# AIRank Release Gate

本文件是 AIRank v0.1 beta 上线前的强制门禁。未全部通过时，不允许声明“可上线”。

可执行门禁命令：

```bash
python3 scripts/release_readiness.py \
  --database-url "$AIRANK_RELEASE_DATABASE_URL" \
  --require-optional-capabilities \
  --require-browser-providers
```

该命令把本文件的核心自动检查脚本化：远端一致性、工作区、运行产物、生产鉴权配置、contracts、acceptance、worker、score、evidence、xinghe-adapter、Web build、Alembic 迁移、capability probe 和消费端网页 Provider readiness。普通自动测试会隔离数据库环境变量，真实 migration 使用 `--database-url` 或 `AIRANK_RELEASE_DATABASE_URL`。生产必须同时满足 `AIRANK_API_AUTH_ENFORCEMENT=required` 与 `AIRANK_AUTH_MODE=yudao`；真实 MySQL、必需 capability 或 ChatGPT / DeepSeek / Kimi / 通义 / 豆包 / 百度 AI 搜索 / 腾讯元宝任一消费端网页 profile 未 READY 时返回非零，不允许用 `dev_only` 结果替代上线通过。

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
| 效果图逐页还原 | 固定 1491x1055，对照 `AIRank素材/操作台/*.png` 的 11 张参考图 | 所有控制台页面必须严格贴近参考图的色彩、图标、字体、间距、卡片数量和首屏结构；不得用“功能通过”替代视觉通过 |
| 控制台移动渲染 | 390x844 截图 | 无横向溢出、主内容可读 |
| 路由切换 | 点击侧栏：工作台、AI 收录体检、企业事实库、买家问题地图、推荐缺口分析、AI 收录包、发布提交、AI 来客助手、报表中心、设置中心；直达 `/console/gaps/questions` | URL 和页面内容变化 |
| Console health | 浏览器 console | 无 error/warning |

## Gate 2：API

后端初始化后启用。

| Check | Command / Evidence | Required |
| --- | --- | --- |
| API 鉴权强制执行 | release gate environment check | `AIRANK_API_AUTH_ENFORCEMENT=required` 且 `AIRANK_AUTH_MODE=yudao` |
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
| snapshot 保存 | DB/test evidence | 每个有效、失败和阻塞任务都有 answer/evidence snapshot 与原始响应 hash |
| citation 保存 | DB/test evidence | 每个引用来源有 citation |
| score 可复现 | score fixture test | 同一输入重复计算一致 |
| 失败显式化 | worker test | 失败不能长期停在 queued |
| 失败现场证据 | DB/browser evidence | Web/App 失败如有现场截图则持久化为不可变对象；失败不冒充未提及 |

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
| 证据包 | `airank.report-evidence-packet.v7` | v4 测量质量门禁 + `airank.evidence-integrity.v2` 源证据与派生状态重建；确定性 ZIP 内含 canonical manifest、可打印 HTML、空白评分表、README、SHA256SUMS，最终 production 双人审核与 packet 级 download receipt；离线校验必须使用 API/回执整包 hash，历史 v1–v6 只读兼容，PDF/Word/数字签名仍 partial |
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

- Re-run `ops/deployment/mysql-bootstrap.sql`; it now repairs common local/Docker Desktop dev-user credentials and grants. If MySQL still reports access denied, inspect `mysql.user` for a more-specific `airank` host record and fix that grant, then rerun `cd apps/api && AIRANK_DATABASE_URL=... python3 -m alembic upgrade head`.
- Provide real yudao/Xinghe/Hermes configuration or explicitly accept a dev_only beta scope before tagging.

## 2026-05-17 18:34 +08:00 Execution

Release Gate: BLOCKED

Commit: current handoff/gate update rebased on `9ca4fc9`

Reviewer: CodexMacPro

Passed:

- GitHub `main`, Gitee `main`, and local HEAD matched at `45b6981` before this verification pass.
- The handoff/gate update was then rebased over remote `9ca4fc9 feat: add mysql worker lease store`.
- Local Docker service `yudao-mysql` is running and exposes MySQL on `127.0.0.1:3306`.
- Bootstrap grant repair was applied inside `yudao-mysql`; the subsequent application-user probe passed for `airank:airank_dev_password`.
- Real migration passed with `cd apps/api && AIRANK_DATABASE_URL=mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike_release_gate?charset=utf8mb4 alembic upgrade head`, using a temporary PyMySQL target for the Python 3.10 Alembic CLI against a fresh release-gate database.
- MySQL-backed Product/API CRUD passed after rebase via FastAPI TestClient with `AIRANK_DATABASE_URL` set to the fresh release-gate database: project create `201`, competitor create `201`, buyer question create `201`.
- MySQL-backed scan persistence passed after rebasing over `fa55f9f`: scan run create `201`, scan task list returned 2 tasks, and `airank_async_jobs` contained 2 queued provider jobs.
- MySQL-backed asset/report persistence passed after rebasing over `46987b8`: asset bundle returned 1 DB-derived asset, report list returned 1 DB report, download receipt returned `201`, and `airank_audit_events` contained 1 receipt event.
- MySQL-backed worker lease passed after rebasing over `9ca4fc9`: claim, heartbeat, succeed, timeout sweep, and explicit retry all passed against `airank_async_jobs`.
- `git diff --check`, `python -m pytest tests/contracts -q` (56 tests), `python -m pytest tests/acceptance -q` (9 tests), `cd apps/worker && python -m pytest -q` (11 tests), `cd apps/web && npm run build`, and `python scripts/agent_control.py gate --write` passed after the rebase.
- Local optional Xinghe probes found creator marketing, workflow runner, and Hermes `/health` endpoints returning `200`.

Still blocked:

- No `YUDAO_BEARER_TOKEN` / `YUDAO_TOKEN` is present in this shell. yudao auth and tenant/user probes therefore remain `dev_only`, not release-ready.
- Crawler and KB configured local endpoints are reachable but do not pass the adapter's configured readiness paths (`/api/crawler-gateway/runtime-status` and `/internal/kb/store-topology` returned non-ready results).
- AI asset bundle and report APIs are MySQL-backed when data exists, but upstream content/report generation still depends on dev/manual seed data until the real yudao/Xinghe/Hermes integration is configured.
- Product has not explicitly accepted a `dev_only` beta scope. Per this gate, do not tag beta or claim release-ready until that approval or real yudao capability is available.

Minimum fix before beta PASS:

- Provide a real yudao bearer token and rerun the capability probe with `AIRANK_AUTH_MODE=yudao`, `YUDAO_PERMISSION_INFO_URL`, and `YUDAO_BEARER_TOKEN`.
- Either map crawler/KB health paths to real service readiness endpoints, or document them as optional `partial` capabilities for the beta scope.
- If product accepts a dev-only beta, record the approval and change the conclusion to `PASS_WITH_RISK` instead of `PASS`.

## 2026-05-17 18:51 +08:00 Execution

Release Gate: BLOCKED

Commit: release-readiness script commit rebased on `9aef7e9`

Reviewer: CodexMacPro

Passed:

- Added executable `python3 scripts/release_readiness.py` gate so release checks can fail CI/local runs instead of living only in this document.
- `python3 -m py_compile scripts/release_readiness.py` passed.
- `python3 -m pytest tests/acceptance/test_release_readiness_gate.py -q` passed 4 tests.
- `python3 -m pytest tests/acceptance -q` passed 13 tests before rebase; after rebase, rerun required because origin added DBVERIFY changes.

Still blocked:

- Release remains blocked by missing real yudao bearer token / tenant-user capability or explicit product approval for a dev-only beta scope.
- The new script must be run from a clean worktree after this commit lands; it intentionally fails on uncommitted files.

## 2026-05-17 19:00 +08:00 Execution

Release Gate: BLOCKED

Commit: release-gate DB grant fix pending commit

Reviewer: CodexMacPro

Passed:

- `ops/deployment/mysql-bootstrap.sql` now creates and grants the local `airank_laike_release_gate` database used by the real release-readiness DB gate.
- Re-applied bootstrap with `docker exec -i yudao-mysql sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < ops/deployment/mysql-bootstrap.sql`.
- Verified PyMySQL application-user connectivity to `airank_laike_release_gate`; `current_user()` resolved to `airank@192.168.65.%`.
- Verified real migration: `cd apps/api && AIRANK_DATABASE_URL=mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike_release_gate?charset=utf8mb4 python3 -m alembic upgrade head` passed.

Still blocked:

- yudao auth / tenant-user capability still needs a real `AIRANK_AUTH_MODE=yudao`, `YUDAO_PERMISSION_INFO_URL`, and bearer token.
- Object storage still reports local `dev_only` unless a production storage driver/configuration is supplied.

## 2026-05-17 19:03 +08:00 Execution

Release Gate: PASS_WITH_RISK

Commit: filesystem object-storage probe pending commit

Reviewer: CodexMacPro

Passed:

- Local yudao login with tenant `1` and admin credentials returned a real access token; token was used only in process memory and not written to files.
- Capability probe with `AIRANK_AUTH_MODE=yudao`, `YUDAO_PERMISSION_INFO_URL=http://127.0.0.1:48080/admin-api/system/auth/get-permission-info`, and the temporary bearer token reported `yudao_auth=ready` and `yudao_tenant_user=ready`.
- Added `AIRANK_OBJECT_STORAGE_DRIVER=filesystem`; its probe creates the root directory, writes a probe object, reads it back, and deletes it.
- Capability probe with `AIRANK_OBJECT_STORAGE_DRIVER=filesystem` and `AIRANK_OBJECT_STORAGE_ROOT=/tmp/airank-release-objects` reported `object_storage=ready`.

Residual risks:

- Optional Xinghe crawler/KB/creator/workflow/Hermes capabilities still report `dev_only` unless real endpoints are configured. They are not required for the MVP gate by the current capability metadata.
- Filesystem object storage is acceptable only for a single-node beta with a mounted persistent directory; multi-node production still needs S3/OSS/minio-class storage integration and probe.

## 2026-05-17 19:05 +08:00 Execution

Release Gate: PASS_WITH_RISK

Commit: `c2ceae4`

Reviewer: CodexMacPro

Passed:

- `python3 scripts/release_readiness.py --database-url mysql+pymysql://.../airank_laike_release_gate?charset=utf8mb4` passed with real yudao token, `AIRANK_PROBE_TIMEOUT_SECONDS=3`, and filesystem object storage environment.
- GitHub and Gitee `main` matched local HEAD `c2ceae4`.
- `python3 -m pytest tests/contracts -q` passed 56 tests.
- `python3 -m pytest tests/acceptance -q` passed 15 tests.
- `cd apps/worker && python3 -m pytest -q` passed 11 tests.
- `cd packages/score && python3 -m pytest -q` passed 3 tests.
- `cd packages/evidence && python3 -m pytest -q` passed 9 tests.
- `cd packages/xinghe-adapter && python3 -m pytest -q` passed 3 tests.
- `cd apps/web && npm run build` passed.
- Alembic offline SQL passed.
- Real Alembic migration passed against `airank_laike_release_gate`.
- Capability probe passed for required MVP capabilities: `yudao_auth=ready`, `yudao_tenant_user=ready`, `object_storage=ready`.

Residual risks:

- Optional Xinghe crawler/KB/creator/workflow/Hermes capabilities remain `dev_only` warnings because endpoints are not configured; current MVP metadata marks them not required.
- Filesystem object storage is a valid single-node beta gate only when backed by a mounted persistent directory. Multi-node production still needs S3/OSS/minio-class storage and probe.

## 2026-05-17 19:19 +08:00 Execution

Release Gate: PASS

Commit: `2d91ab4`

Reviewer: CodexMacPro

Passed:

- `python3 scripts/release_readiness.py` returned `Result: PASS` from a clean worktree.
- GitHub and Gitee `main` matched local HEAD `2d91ab4`.
- `python3 -m pytest -q` passed 99 tests with 6 opt-in real integration tests skipped by default.
- Real release-gate MySQL integration passed against `airank_laike_release_gate`: 5 tests passed, yudao test skipped by flag.
- Full real integration passed against local yudao and MySQL: 6 tests passed.
- `python3 scripts/release_readiness.py` passed contracts 56, acceptance 15, worker 11, score 3, evidence 9, xinghe-adapter 5, Web build, real integration 6, Alembic offline SQL, real Alembic migration, and capability probe.
- Required MVP capabilities were ready: `yudao_auth=ready`, `yudao_tenant_user=ready`, `object_storage=ready`.
- Release-gate DB grants now include Docker bridge host `172.20.%`, and real integration tests now assert the configured database name instead of hard-coding `airank_laike`.

Residual risks:

- Optional Xinghe crawler/KB/creator/workflow/Hermes capabilities remain `dev_only` warnings because endpoints are not configured; current MVP metadata marks them not required.
- Filesystem object storage is acceptable for this single-node beta gate only when backed by a mounted persistent directory. Multi-node production still needs S3/OSS/minio-class storage and probe.

## 2026-05-17 19:28 +08:00 Browser QA

Release Gate: PASS

Commit: this Web QA commit

Reviewer: CodexMacPro

Passed:

- Started real FastAPI on `127.0.0.1:8000` with MySQL `airank_laike`.
- Ran `scripts/seed-fixtures.sh` to seed `tenant_demo/project_demo` into real MySQL before browser QA.
- Started Vite on `127.0.0.1:5173` with `/api` dev proxy to the real API.
- Desktop `/console` rendered meaningful AIRank content, no framework overlay, no fallback banner, and no fresh browser console warnings/errors.
- Clicked required routes: `工作台`, `推荐缺口分析`, `AI 收录包`, `报表中心`; URL and page content changed for each route, with no fallback banner and no fresh console warnings/errors.
- Real API returned `200 OK` for `/api/v1/projects/project_demo/asset-bundle` and `/api/v1/projects/project_demo/reports`; those pages no longer depend on frontend fallback fixture data during local beta QA.
- Mobile 390x844 `/console` rendered with `documentElement.scrollWidth == innerWidth == 390`, so there is no page-level horizontal overflow.

Residual risks:

- Browser QA covers the Vite dev build and local FastAPI/MySQL path. Production reverse-proxy/CDN headers still need environment-specific verification during deployment.

## 2026-08-08 03:23 +08:00 Evidence Productization Gate

Release Gate: BLOCKED

Commit: `4f14da1`

Reviewer: Codex

Passed:

- Clean worktree, diff check, tracked-runtime-artifact check, and production auth configuration (`required` + `yudao`).
- Contracts 98, acceptance 39, worker 17, score 7, evidence 11, and Xinghe adapter 5 tests.
- Web production build, real MySQL integration `7 passed, 1 skipped`, Alembic offline SQL, and real MySQL migration.
- Release runner now loads all internal package source paths before the browser-provider gate; the previous `ModuleNotFoundError` false blocker is removed.
- Separate browser product QA passed 13 routes at desktop and 390px mobile, and the real evidence center showed server-aggregated ScanRun totals without cross-run mixing.

Blocking conditions:

- Local branch `codex/evidence-productization` is not merged or synchronized to GitHub/Gitee `main`; both remote refs remain at `495655c`.
- Production Yudao permission-info and tenant/user capability are not configured in this gate environment.
- Object storage is still local `dev_only`; production durable object storage has not passed its probe.
- Consumer Web/App collection is not ready: browser readiness was `0/4`; Doubao, Qianwen, and Kimi require authenticated sessions, while DeepSeek requires login/human verification. API sampling success does not satisfy this evidence grade.
- Node 20.18.2 remains below Vite's supported minimum; the build passes but runtime must be upgraded before launch.

Decision:

- Keep commercial launch at `NO-GO`. Do not use the earlier 2026-05-17 PASS as evidence for the expanded GEO productization scope.

## 2026-08-08 Durable Evidence Object Gate

Release Gate: BLOCKED

Commit: pending evidence-object commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Browser screenshots are copied from temporary capture paths into content-addressed filesystem or S3/MinIO storage before a sample is committed as valid.
- Evidence object reads are authenticated and tenant-scoped; the API verifies stored SHA-256 and byte size before returning bytes, and the console renders them through an authenticated Blob request.
- Full local regression passed: `207 passed, 10 skipped`; Web build passed and npm high-severity audit reported zero vulnerabilities.
- Real MySQL integration passed `8 passed, 2 skipped`, including object-reference lookup, durable readback, integrity verification, and cross-tenant rejection.
- Real local MinIO integration passed its write/read/delete test, left zero probe objects, and removed the temporary test bucket. No object-storage credentials were written to source, Git, test output, or reports.
- Production configuration now rejects filesystem-only storage, plaintext S3 endpoints, and `AIRANK_S3_ALLOW_HTTP=true`; CI uses Python 3.11.

Blocking conditions:

- This branch is not merged into GitHub/Gitee `main`.
- Production Yudao authentication and consumer Web/App Provider sessions are still unavailable for the final gate.
- The successful MinIO check used a local HTTP endpoint; the production HTTPS S3/MinIO environment remains unverified.
- The current workstation uses Python 3.9.6 and Node 20.18.2. Both are now explicitly blocked by the production runtime gate; deployment requires Python 3.11+ and Node 20.19+ or 22.12+.

Decision:

- Durable screenshot evidence is implemented and locally verified, but commercial launch remains `NO-GO` until the remaining external and production-runtime gates pass.

## 2026-08-08 Core Skill Evaluation Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: pending core Skill evaluation commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Eight versioned internal Skills each passed contract, holdout, and adversarial suites: `24/24` executable cases.
- The gate fixed four discovered guardrail defects: empty facts no longer generate a page blueprint, negated excerpts no longer support a positive fact by substring, unrelated ranking language no longer assigns a brand rank, and invalid observation rates/counts are blocked.
- Promotion Evidence Ledger binds the registry, eval corpus, promotion evidence list, implementation, and evaluation engine by SHA-256.
- Admin Skill APIs require trusted `airank:skill:admin` permission. The auth middleware overwrites a spoofed client permission header; the contract test proves an ordinary dev session receives `403 AUTH_PERMISSION_FORBIDDEN`.
- Full local regression passed `213 passed, 10 skipped`; core Skill package passed 7 tests; Web build and npm audit passed.
- Browser QA showed 8 Skills, 8 local passes, 0 promotion-eligible, and 8 retained partial. Desktop had no console warning/error; the 390px check had no page-level horizontal overflow and contained the wide table scroll inside its card.

Blocking conditions:

- All eight Skills remain `partial`. Local tests are not accepted as substitutes for the real queue, reviewed labeled benchmark, Provider citation benchmark, reviewed fact/content benchmark, or real T0/T+7 evidence required by each promotion policy.
- Production Yudao must expose and grant the configured Skill admin permission before this console is production-accessible.
- The broader commercial blockers from the durable evidence gate remain unchanged.

## 2026-08-08 Knowledge Governance Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: pending knowledge-governance commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Added tenant/project-scoped open-conflict listing and a 1—365 day knowledge-governance window derived from current KnowledgeSource, approved FactRevision, and FactConflict records. The read model reports expired/expiring sources and facts plus open conflicts without mutating source, fact, or conflict history.
- Fact eligibility is now evaluated against current source status, source validity, fact validity, and open conflicts. A conflict immediately blocks previously approved facts; a recorded human resolution restores eligibility only when every other evidence gate still passes.
- MySQL datetimes are normalized to UTC before API serialization. Browser QA proved source-list and alert timestamps now match; the previous eight-hour divergence is removed.
- Duplicate registration of the same unordered revision pair now returns controlled `409 STATE_CONFLICT` with the existing conflict state instead of leaking a MySQL unique-key exception.
- The real console shows governance counts, alert details, revision IDs, required resolution notes, and manual resolution choices. Browser QA proved empty-note blocking and a real MySQL transition from four actions/open conflict to three actions/no open conflict; the approved source-backed fact returned to eligible.
- Desktop browser QA at 1024px reported no page or resolution-form horizontal overflow and no console warning/error. Screenshot review found and fixed unreadable vertically wrapped fact-card titles; the final grid uses two readable 361px columns at that viewport.
- Full local regression passed `214 passed, 11 skipped`; real MySQL passed `9 passed, 2 skipped`; absorption matrix stayed at 12 sources / 64 rows / 21 GEO Skills; core Skill eval stayed `24/24` with `0` promotion-eligible; Web build and npm high-severity audit passed with zero known vulnerabilities.

Not claimed as passed:

- The new conflict form was not revalidated at a physical 390px viewport in this slice. The in-app browser rejected a nested narrow-viewport preview under its URL security policy, so only the responsive CSS/build and earlier console-wide 390px evidence remain. A direct device-width rerun is still required before production sign-off.
- The production readiness runner remains `BLOCKED`: branch not merged to either remote `main`, production HTTPS S3/MinIO absent, Python `3.9.6` and Node `20.18.2` below the enforced runtime floor, Yudao permission-info missing, and consumer browser Provider readiness `0/4`.
- No customer-owned source-update worker, incremental re-embedding, hybrid retrieval, production Yudao identity, or real external publishing credential was supplied or verified.

Decision:

- Knowledge expiry and conflict handling is now an operable, evidence-backed slice, but AIRank remains `NO-GO` for commercial launch until the production and external gates above pass.

## 2026-08-08 Knowledge Source Revision Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this knowledge-source-revision commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Knowledge source updates create immutable child revisions and exact-boundary segments; the previous active source becomes `stale` without deleting its content, hash, or audit identity.
- Approved facts backed by a stale source dynamically lose generation eligibility with `source_stale`; raw evidence is not rewritten and an operator must re-propose/review the fact against current evidence.
- Project-scoped search only considers active, currently valid source segments. Results expose source/version, exact text, character boundaries, content hash, match mode, and matched terms.
- Retrieval truthfulness is explicit: the API and console report `lexical_only` and `vector_status=not_configured`. No vector, embedding, or hybrid claim is made.
- Targeted contract/acceptance tests passed `18`; real MySQL integration passed `9` with `2` external-service skips; Web production build passed with the already-known Node floor warning.
- Real browser QA updated a MySQL-backed source from v1 to v2, observed the old fact become `source_stale`, retrieved the v2-only phrase with exact boundaries/hash, and confirmed a v1-only phrase was absent from current retrieval. Desktop and direct 390×844 viewport checks had no page-level overflow and console `0 error / 0 warning`.
- Screenshot review found and fixed a product layout defect where the full-width guide button compressed Chinese copy into a vertical column.

Not claimed as passed:

- Customer-owned automatic source synchronization, parser connectors, embeddings, incremental re-embedding, vector/hybrid retrieval, and retrieval relevance benchmarks are not implemented or verified.
- The local browser used `dev_only` authentication for product-flow QA. This does not satisfy production Yudao authentication.
- The commercial blockers remain: branch not merged to both remote `main`, production HTTPS S3/MinIO absent, Python/Node below the enforced floor, Yudao permission-info missing, and consumer Web/App Provider readiness `0/4`.

Decision:

- Immutable source revision and truthful current-source retrieval are now operable, but the overall product remains `NO-GO` for commercial launch.

## 2026-08-08 Buyer Question Governance Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: pending buyer-question-governance commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- `research.intent-miner` `1.1.0` now compiles provided seeds and deterministic template candidates into a versioned taxonomy with provenance, stable question versions, Unicode/punctuation-aware deduplication and separate blind/assisted/comparison/fact-verification Cohorts.
- Persisted QuestionMap manifests and BuyerQuestionRevision records are immutable; human decisions append BuyerQuestionReview events. Suggested candidates do not enter scans, and a confirmed question can only enter a ScanRun with the exact Cohort stored in its current immutable revision.
- Alembic `20260808_0009` passed real MySQL migration and 45-table verification. Its online path safely resumes partially applied MySQL DDL, while its offline path now generates complete deployment SQL without attempting live schema inspection.
- Local regression passed `220 passed, 12 skipped`; focused governance/Skill tests passed `39`; core Skill evaluation stayed `24/24`, with all 8 Skills honestly retained as `partial`.
- Real MySQL integration passed `10 passed, 2 skipped`; Web production build and npm high-severity audit passed with zero known vulnerabilities.
- Real browser QA compiled and reviewed a MySQL-backed question map, queued the matching blind question, rejected a mismatched comparison run, and replayed the same logical input under taxonomy `airank-question-taxonomy-v1.1.0` without duplicating questions. Desktop and 390×844 checks showed no page-level overflow; the final page had `0 error / 0 warning`.

Blocking conditions:

- Production Python 3.11+ and Node 20.19+ or 22.12+ are not active on this workstation.
- Production Yudao identity/permission-info and HTTPS S3/MinIO are not configured in the release environment.
- Consumer browser Provider readiness remains `0/4` because login or human verification is required; API L3 success does not satisfy Web/App evidence.
- The branch is synchronized as a feature branch only; GitHub/Gitee `main` remain outside this task's merge authority.

Decision:

- Buyer-question governance is an operable, evidence-backed product slice. AIRank remains `NO-GO` for commercial launch until the production and external gates above pass.

## 2026-08-08 Observed Buyer Query Provenance Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this observed-query-provenance commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- `research.intent-miner` `1.2.0` accepts only observation-shaped immutable references with an explicit evidence grade. Invalid manual references are ignored rather than promoted to observed-query evidence.
- Tenant/project-scoped M1 observation imports preserve source metadata, rights attestation, payload/content hashes, source-local occurrence counts and provenance. Identical payload replay is idempotent.
- Email, China mobile and China identity-number patterns are blocked before persistence. The raw PII text is absent from the batch manifest, safe observation records, compiled provenance and browser output.
- `occurrence_count` is consistently labeled as source-local frequency, not search volume. Customer-provided records remain `user_provided_snapshot` and explicitly “not independently verified.”
- Alembic `20260808_0010` reached real MySQL head with 47 AIRank tables. The migration recovered safely after MySQL rejected the initial reserved column name; the final schema uses `source_row_number`.
- Full local regression passed `225 passed, 13 skipped`; real MySQL integration passed `11 passed, 2 skipped`; core Skill evaluation remained `24/24` with `0` promotion-eligible and all 8 Skills retained as `partial`.
- Real browser QA imported one safe question with source-local frequency 7, blocked one PII row, compiled the observed candidate, applied human confirmation, and proved persistence after reload. At a 390px effective viewport, html/body scroll width stayed 390px and the final console had `0 error / 0 warning`.

Blocking conditions:

- M2 automatic customer-source connectors, M3 sampled calibration, industry coverage benchmark and follow-up-chain evaluation are not implemented; M1 customer-provided data is not proof of market-wide demand.
- Production Python 3.11+ and Node 20.19+ or 22.12+ are not active on this workstation.
- Production Yudao identity/permission-info and HTTPS S3/MinIO are not configured in the release environment.
- Consumer browser Provider readiness remains `0/4`; API success does not satisfy Web/App evidence.
- The branch is synchronized only as `codex/evidence-productization`; remote `main` remains outside this task's merge authority.

Decision:

- M1 observed-query provenance is operable and evidence-backed. AIRank remains `NO-GO` for commercial launch until connector/calibration and broader production gates pass.

## 2026-08-08 Measurement Data Quality Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this measurement-quality commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Added content-addressed `airank.measurement-quality.v1` reports with 10 blocking checks across sample/signature cardinality, duplicate sample IDs/contracts, status partition, valid samples/rate, answer hash, raw-response hash and explicit mention classification.
- Normal valid-but-not-mentioned answers remain in the valid denominator. Missing citations, citation-support review, fact-accuracy review and repeat stability are explicit known limitations rather than invented values.
- Retest reports are `generated` only when both run-quality reports are publishable and the baseline/compare sample contracts are comparable. Otherwise they persist as `quality_blocked` and the observation window remains `completed_with_limitations`.
- Report downloads fail closed with `409 REPORT_QUALITY_BLOCKED` for quality-blocked and legacy reports without the signed quality manifest. No audit receipt is written for a rejected download.
- Full local regression passed `229 passed, 13 skipped`; real MySQL integration passed `11 passed, 2 skipped`; core Skill evaluation remained `24/24` with all 8 Skills retained as `partial`.
- Real MySQL proved a 12-task run with only 1 valid sample is non-publishable and reports the low valid rate plus missing raw failure snapshots. Browser QA showed the quality-blocked report, truthful limitation copy and disabled download at a 390px effective viewport with no page overflow and `0 error / 0 warning`; a direct real API call returned the expected 409.

Blocking conditions:

- Superseded by the `airank.measurement-quality.v2` gate below: Consumer Web/App screenshot and source-panel integrity are now blocking inputs. Actual App collection remains unavailable.
- Full warehouse rebuild checks, derivation lineage, and HTML/PDF/DOCX visual/accessibility gates are not implemented.
- Production runtime, Yudao, HTTPS object storage, consumer browser Provider sessions and remote-main blockers from the prior release gate remain unchanged.

Decision:

- AIRank can now distinguish a stored report from a publishable customer report. Commercial launch remains `NO-GO` until the broader evidence and production gates pass.

## 2026-08-08 Surface-Specific Evidence Integrity Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this surface-evidence commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Upgraded the content-addressed quality contract to `airank.measurement-quality.v2`. Every task sample now has a separate Evidence Manifest; analytical labels cannot upgrade API, Consumer Web, Consumer App, or manual-import evidence.
- The report executes 21 checks: the prior 10 sample/data checks plus manifest cardinality/uniqueness, surface-level matching, request metadata, trace IDs, API provider audits, Consumer screenshots, source-panel inspection/consistency, App capture metadata, and manual-import provenance.
- API samples require an actual `airank_provider_request_audits` link. Consumer Web/App samples require immutable screenshot references and SHA-256. Source panels must be explicitly `captured` or `not_present`; citations on a Consumer surface require an immutable source-panel object. App samples additionally require content-addressed device/App capture metadata, while manual imports require a source SHA-256.
- Browser capture now records a conservative source-panel state. Visible external links tied to answer text are captured using the immutable whole-page screenshot and stored as a distinct source-panel object; a page with no accepted source links records `not_present` instead of leaving provenance ambiguous.
- The Evidence Center loads the real quality API for the selected run and shows per-surface sample, valid, evidence-complete, screenshot, source-panel, and blocker counts. Sample drill-down renders the explicit source-panel status.
- Report listing and download now require both baseline and comparison quality manifests to use the current v2 contract. A previously `generated` v1/legacy report is exposed as `quality_blocked` and cannot create a download audit receipt until it is recomputed.
- Full local regression passed `232 passed, 13 skipped`; real MySQL integration passed `11 passed, 2 skipped`; Web TypeScript/Vite build passed with the known Node patch-version warning.
- Real MySQL and browser QA proved fail-closed behavior with one valid Consumer Web sample: valid rate `1.0`, not-mentioned count `1`, source panel explicitly `not_present`, but no screenshot object. The report blocked only `consumer_screenshots_complete`; the UI displayed `web / consumer_web`, `1 valid`, `0 evidence complete`, and `1 blocker`. The 390px effective viewport had no page overflow and browser logs contained `0 error / 0 warning`. Screenshot: `/tmp/airank-surface-evidence-mobile.png`.

Blocking conditions:

- Consumer App task execution is still unimplemented, so its stricter manifest is a fail-closed contract rather than a passed production collector.
- Consumer browser Provider readiness remains `0/4`; the new Web persistence path still needs real logged-in platform sessions with screenshots and source panels across the four planned platforms.
- Full warehouse rebuild checks, derivation lineage, HTML/PDF/DOCX visual/accessibility gates, production runtime, Yudao, HTTPS object storage, external Publisher, remote-main synchronization, and end-to-end customer reporting remain open.

Decision:

- AIRank can no longer publish a Consumer-surface report when the database has only answer text and hashes. Commercial launch remains `NO-GO` until real Consumer sessions and the broader production gates pass.

## 2026-08-08 Immutable Scan Failure Evidence Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this immutable-failure-evidence commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Every real scan task now writes an immutable AnswerSnapshot and EvidenceSnapshot, including failed and blocked slots. Failure snapshots keep an empty answer, no answer hash, a content-addressed raw-failure hash, request metadata, status, error taxonomy and any available external trace.
- Browser errors captured after page launch preserve a failure-scene screenshot. The temporary path is removed from persisted metadata after the bytes are copied to immutable object storage; authenticated reads continue to recheck SHA-256 and length.
- Failure taxonomy separates user/external-action blockers (login, captcha, auth, model endpoint, quota) from timeouts and operational network/upstream/parser failures. None of these are classified as brand not-mentioned or included in the valid answer denominator.
- A real MySQL mixed run passed with one valid, not-mentioned sample and one blocked sample. Both had raw-response hashes, `raw_response_hashes_present` passed, and the blocked sample remained outside the not-mentioned metric.
- A second real run used an actual Qianwen API response together with an actual Qianwen Consumer Web timeout. The completed batch showed `1/2` valid, one valid not-mentioned answer, one failed Web slot, and an immutable failure-scene screenshot.
- Browser QA drilled into the failed Web sample and displayed “失败，不计品牌分类”, no answer hash, an immutable raw-response hash, EvidenceSnapshot ID, Consumer Web evidence grade and the verified screenshot object. Mobile rendering produced no browser error/warning. Screenshot: `/tmp/airank-failure-evidence-mobile.png`.
- Full local regression passed `240 passed, 14 skipped`; real MySQL integration passed `12 passed, 2 skipped`; focused contracts passed `35`; Web build and npm high-severity audit passed with zero known vulnerabilities. The yaojingang source lock was rechecked against all current relevant repository HEADs and remained unchanged; the absorption matrix still validates `12 sources / 64 rows / 21 GEO skills`.

Blocking conditions:

- The mixed run is intentionally non-publishable because its valid-sample rate is only `0.5`; preserving failed evidence does not lower the report-quality threshold.
- Consumer App collection, four-platform logged-in Consumer Web repetition, production Yudao, HTTPS object storage, external Publisher receipts, production Python/Node versions, remote-main synchronization and end-to-end customer reporting remain open.

Decision:

- AIRank can now audit why a scan slot failed without corrupting visibility metrics or losing the browser failure scene. Commercial launch remains `NO-GO` until the broader production gates pass.

## 2026-08-08 Durable Scan Worker Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: this durable-scan-worker commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- MySQL-backed brand checks now default to durable `scan.provider` dispatch. The API returns the queued ScanRun and no longer holds the request open for a full Provider batch; inline execution requires an explicit diagnostic setting.
- The first claimed job atomically owns the ScanRun. Provider calls and evidence-persistence phases refresh its heartbeat. Concurrent workers defer redundant triggers without consuming attempts, preventing the queue from being drained while the owner is alive.
- Terminal replays settle jobs from persisted task state without another Provider call. If the owner lease expires with an unknown external outcome, automatic replay is suppressed and the run fails closed with `SCAN_RUN_LEASE_EXPIRED`.
- Every unpersisted slot in an expired run receives an immutable empty-answer AnswerSnapshot and EvidenceSnapshot with a raw-response SHA-256, task request metadata, explicit infrastructure capture mode and `provider_response_available=false`.
- The console distinguishes “queued” from “completed”, routes new queued checks to Task Center, and polls runs/tasks for durable asynchronous progress.
- Real browser QA observed the same Qianwen API task move from `queued` to `completed` via polling. Model `qwen3.6-plus`, a real Provider request ID, answer/raw-response SHA-256, linked request audit and immutable EvidenceSnapshot were all visible; the valid not-mentioned result remained in the denominator.
- That QA exposed a false-positive quality gate: one successful sample was labeled deliverable even though repeat stability was unavailable. `airank.measurement-quality.v4` requires three distinct sample indexes and sessions for every question/Provider/Cohort/surface/model group, and Consumer Web/App evidence must additionally prove that the collector entered a fresh conversation. Single samples, reused sessions, and unverified Consumer conversations are non-publishable.
- Internal Worker exceptions also fail every unpersisted task/job and create immutable failure snapshots before returning a terminal error; they cannot leave a failed run with queued tasks and missing evidence.
- Full local regression passed `246 passed, 17 skipped`; real MySQL integration passed `15 passed, 2 skipped`; Web TypeScript/Vite build passed and npm reported zero known vulnerabilities. The Node patch-version warning remains open.

Blocking conditions:

- Scan execution still persists an entire run in one batch. One-task-per-worker transactions, attempt-versioned evidence and safe task-level retry are not implemented, so this capability remains `partial`.
- Four-platform same-cohort repetition, Consumer App collection, four logged-in Consumer Web sessions, production Yudao, HTTPS object storage, customer Publisher receipts, supported production runtimes, remote-main synchronization and complete customer-report E2E remain open.

Decision:

- AIRank now has a truthful durable queue boundary and fail-closed crash behavior for real scans. It is not yet commercially launchable because task-level durability and the broader external production gates are incomplete.

## 2026-08-08 Task-Level Scan Durability Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Commit: pending task-level-scan-durability commit on `codex/evidence-productization`

Reviewer: Codex

Passed:

- Each `scan.provider` job now executes exactly one sampling slot. Different workers may process sibling slots in the same run without sharing a run-level in-memory result buffer.
- A completed slot persists AnswerSnapshot, EvidenceSnapshot, citations, Provider request audit, task/job state and attempt state atomically. Mid-run MySQL verification observed one durable snapshot while the sibling task remained queued and the run remained `running`.
- Run metrics and terminal status are recomputed exclusively from durable rows and only after every slot is terminal. Normal not-mentioned samples remain in the valid denominator; failed and blocked samples remain outside it.
- Alembic `20260808_0011` created `airank_scan_task_attempts`. The ledger records job, attempt number, Provider/surface, start/end, outcome, linked answer/evidence, external request ID and structured error metadata.
- A timed-out external call with unknown outcome is not replayed. Only that slot receives immutable `SCAN_TASK_LEASE_EXPIRED` evidence and an `unknown` attempt; queued/completed sibling slots remain untouched.
- Terminal job requeue is idempotent and does not call the Provider again. Internal dependency failure writes failure evidence and a failed attempt for only the claimed slot.
- The evidence-detail API and console expose the Worker attempt chain instead of leaving the audit ledger database-only.
- A fresh real Qianwen task completed through the task-level Worker with model `qwen3.6-plus`, a real external request ID and a `succeeded` attempt linked to immutable answer/evidence snapshots. The valid not-mentioned answer remained in the denominator, while the single-session run remained correctly quality-blocked.
- Browser QA displayed attempt #1, its job, real request ID, start/end time and linked evidence. At 390×844 the document width stayed 390 with no page-level overflow; a fresh authenticated tab had 0 console errors and 0 warnings. The isolated QA tenant was removed afterward with zero rows remaining.
- Full local regression passed `247 passed, 17 skipped`; real MySQL integration passed `15 passed, 2 skipped`; the schema head is `20260808_0011` with 48 AIRank tables. Web TypeScript/Vite build and npm high-severity audit passed; Node `20.18.2` remains below the required production patch floor.

Blocking conditions:

- Distributed circuit-breaker state, transactional tenant quota enforcement, multi-upstream routing, four-platform same-cohort repetition, Consumer App collection, four logged-in Consumer Web sessions, production Yudao, HTTPS object storage, customer Publisher receipts, supported production runtimes, remote-main synchronization and complete customer-report E2E remain open.

Decision:

- The batch-crash evidence-loss blocker is closed. Provider reliability remains `partial`, and AIRank remains commercial `NO-GO` until the remaining external and production gates pass.

## 2026-08-08 Consumer Conversation and L3 Readiness Gate

Release Gate: BLOCKED / COMMERCIAL NO-GO

Passed:

- Consumer Web collection fails closed unless it can activate a visible new-conversation control and find a usable prompt input afterward. The verification record is preserved in request metadata.
- `airank.measurement-quality.v4` adds verified Consumer conversation isolation and failed-run publishability checks. A failed ScanRun remains auditable but can never become a deliverable report.
- Chinese slider-verification text is classified as CAPTCHA evidence instead of a model answer. Failure evidence retains the original-response hash, immutable screenshot reference and verified conversation-isolation metadata.
- A real Qianwen Web submission reached an isolated new conversation and then produced a slider challenge. The durable MySQL path stored ScanRun `failed`, Task `SCAN_PROVIDER_BLOCKED`, Sample `blocked`, immutable screenshot/hash and a v4 non-publishable quality report. Validation data was removed afterward.
- Production release checks now require explicit Yudao auth, `AIRANK_ENV=production`, S3/MinIO and encrypted object-storage transport. Local defaults no longer pass those individual checks.
- Full regression: `321 passed, 22 skipped`; real MySQL integration: `20 passed, 2 skipped`; Web build passed using Node 24.14.0.

Blocking conditions:

- Consumer L3 readiness is `0/4`: Qianwen and DeepSeek require human verification; Doubao and Kimi require authenticated browser profiles.
- Production Yudao and HTTPS S3/MinIO are not configured, remote `main` refs are not synchronized, and the complete four-platform customer-report E2E has not passed.

Decision:

- L2 input discovery is no longer counted as Provider readiness. AIRank remains a commercial `NO-GO` until L3 generation, production infrastructure and end-to-end delivery gates pass.

## 2026-08-08 Three-Provider API Repetition Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Qianwen, Doubao and DeepSeek each completed three real, independent API samples for the same blind buyer question through the durable Worker path.
- All nine tasks completed with nine valid samples, nine distinct per-provider sessions, nine raw-response hashes, nine external request traces and nine Provider request audits. Every Provider used one recorded route.
- All nine valid answers did not mention the test brand and remained in the valid denominator.
- `airank.measurement-quality.v4` returned `publishable=true` with no blocked checks for this API-only visibility run.
- Provider-specific output limits were validated: Qianwen and DeepSeek accepted 256 tokens for the concise probe, while Doubao required 4096 to avoid `PROVIDER_EMPTY_RESPONSE`. The global 256-token experiment remained non-publishable and was not used as proof.
- The isolated tenant and temporary object directory were removed after verification. Provider keys were loaded only from local private env files and were neither printed nor committed.

Limitations and blockers:

- The quality report explicitly retained `valid_samples_have_no_provider_citations`, `citation_support_not_evaluated` and `fact_accuracy_not_evaluated`. This gate supports an API visibility result only.
- Kimi repetition remains blocked pending rotation and secure injection of the key previously exposed in conversation history.
- Consumer Web/App evidence remains a separate `0/4` L3 gate and cannot be upgraded by API results.

Decision:

- Three-provider API repetition is deliverable within its stated evidence scope. Four-platform measurement, citations, fact accuracy, Consumer surfaces and the overall commercial release remain `partial/blocked`.

## 2026-08-08 Customer Evidence Packet Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- `airank.report-evidence-packet.v1` is a deterministic, content-addressed customer evidence artifact. It binds the report, baseline and comparison runs, v4 quality gates, metric formulas, limitations, risks, samples, citations and stored evidence objects without duplicating raw answer bodies.
- Packet creation fails closed for legacy or non-publishable quality contracts, missing runs, inconsistent sample counts, incomplete immutable evidence, missing API request audits, unknown citations and invalid SHA-256 values.
- Alembic `20260808_0018` adds an immutable packet ledger with tenant/report/schema uniqueness, idempotency protection, object reference and creation audit. Downloads require a matching packet ID and content hash and record the trusted authenticated actor.
- The console performs create/replay, object download, browser SHA-256 verification, file save and packet-bound receipt in that order. Empty or quality-blocked projects do not fabricate a report.
- Full regression passed `339 passed, 24 skipped`; real MySQL integration passed `22 passed, 2 skipped`; Node 24 TypeScript/Vite build passed; npm high-severity audit reported zero vulnerabilities. The absorption matrix remains `13 sources / 67 rows / 21 GEO skills`.
- Browser QA on the real reports route showed the honest empty state and blocked generation notice, no page-level overflow at 1024px, and zero warning/error logs.

Limitations and blockers:

- HTML/PDF/Word renderers, digital signing, a public verification page and the formal blank scorecard remain `partial`.
- Four-platform same-cohort repetition is incomplete because the exposed Kimi credential must be rotated before use. Consumer Web/App L3 remains `0/4`.
- Production Yudao, production HTTPS S3/MinIO, customer publishing credentials and a real T0/T+7/T+14/T+30 observation window are external blockers.

Decision:

- AIRank now has a tamper-evident JSON delivery artifact for qualified reports. It is not commercially launchable until the external production and observation gates pass.

## 2026-08-08 Fact Accuracy Evidence Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Answer claims now distinguish citation-support claims from brand and competitor factual claims, with subject entity, exact immutable answer boundaries and claim hash.
- Alembic `20260808_0019` adds append-only fact-accuracy reviews. Commercially eligible reviews require a current, approved, human-reviewed, public/redacted FactRevision, a current source, no open conflict and an exact excerpt boundary inside the source segment.
- `accurate`, `inaccurate`, `outdated` and `insufficient` remain distinct. `insufficient` does not bind a fabricated FactRevision, and fact accuracy is only calculated when every registered brand/competitor factual claim has a decisive current review.
- Superseding or invalidating a fact/source preserves historical reviews while automatically removing them from current metrics. AI-derived labels cannot overwrite the raw claim or human review history.
- Retest reports and `airank.report-evidence-packet.v4` recompute fact claim count, final production review coverage, accuracy, citation support and source-governance eligibility from current MySQL evidence. The packet stores hashes and boundaries, not copied answer/source or human-note bodies; historical v1/v2/v3 packets remain readable.
- The Evidence Center supports exact claim registration and human verdicts. Desktop and 390x844 browser QA completed the path, showed 100% only for the isolated 1/1 QA fact, kept the run blocked for missing repetition/citations, then removed the QA project. Reloading the real project preserved all nine valid not-mentioned samples and reported zero console errors.
- Full local regression passed `354 passed, 25 skipped`; real MySQL integration passed `23 passed, 2 skipped`. They cover exact boundaries, idempotency, audit, recalculation, packet hash validation and stale-evidence invalidation. Node 24 TypeScript/Vite build and the high-severity npm audit passed with zero known vulnerabilities.

Limitations and blockers:

- A production double-review queue, labeled inter-reviewer benchmark and customer-reviewed fact dataset remain incomplete; the capability therefore stays `partial`.
- Four-platform same-cohort repetition, Provider-native citation support, Consumer Web/App L3, production Yudao, HTTPS object storage, customer publishing credentials and T0/T+7/T+14/T+30 observation evidence remain open.

Decision:

- The previous fact-accuracy placeholder is replaced by a traceable human-evidence workflow. AIRank remains commercial `NO-GO` until the external production, reviewer-quality and observation gates pass.

## 2026-08-08 Durable Retest Scheduler Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- `apps/scheduler` durably dispatches due T0/T+7/T+14/T+30 observation windows. T0 records the completed baseline as an immutable anchor; later windows create new ScanRuns and queue normal governed `scan.provider` jobs.
- Scheduled retests clone the baseline task's frozen question text, Prompt version, Provider, Cohort, collector surface, evidence level and model-route context. Editing the current buyer question after T0 does not change the retest contract, and every cloned sample receives a fresh session ID.
- Missing or incomplete baselines, missing baseline tasks and legacy tasks without a frozen Prompt fail closed. The window becomes `blocked`, no Provider job is fabricated, and a structured append-only audit event records the reason.
- Worker and Scheduler are tenant-safe by default. Project scope requires tenant scope; global multi-tenant processing requires both a dedicated environment opt-in and `--allow-global-scope`. Worker `--dry-run` returns before Provider/Publisher setup, while `--drain --max-jobs` bounds mutation.
- A real database preview found 71 due historical `scan.provider` jobs globally and deliberately left them unclaimed. A tenant-scoped preview returned only that tenant's eligible count.
- Full regression passed `368 passed, 26 skipped`; real MySQL integration passed `24 passed, 2 skipped`. The scheduler integration verifies frozen-Prompt cloning after question edits, fresh sessions, exact queue scope, idempotent dispatch, audit history and a failed comparison run becoming a truthful `quality_blocked` report with a `completed_with_limitations` window.

Limitations and blockers:

- The scheduler was validated by controlled due timestamps. No real customer publication has yet elapsed through T+7, T+14 or T+30, so this is scheduling and evidence-integrity proof, not observed GEO uplift.
- A production service unit/container, alerting, leader-election operating procedure and long-duration crash/load test remain incomplete.
- Four-platform same-cohort repetition, Consumer Web/App evidence, production Yudao, production HTTPS object storage and customer publishing credentials remain open.

Decision:

- The previous manual-only observation-window gap is closed at the durable application and database-contract level. Effect monitoring remains `partial`, and AIRank remains commercial `NO-GO` until real elapsed observations and the other production gates pass.

## 2026-08-08 Citation Source Registry Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- AIRank now derives a project Source Registry exclusively from exact DNS hosts already present in immutable Citation records. Unknown hosts remain `unclassified`; the service does not infer categories or authority from a parent domain, brand name or model output.
- Alembic `20260808_0020` adds append-only source-classification revisions with category, type, ecosystem, confidence, authority, usage, risk, evidence, validity, trusted reviewer, supersedes link, request hash and idempotency key.
- Manual review requires an actually observed host, tenant/project scope, a trusted authenticated actor and the latest revision ID. Stale updates fail closed; old revisions and original Citation evidence are retained.
- Replaying an idempotency key for an older revision marks that historical revision as replayed while preserving the newest revision as current.
- Real MySQL integration passed `25 passed, 2 skipped`, including the unclassified, v1, replay, stale-conflict, v2, audit and cleanup paths. Browser QA completed unclassified to v1 to v2 through the Evidence Center; desktop and 390px layouts had no page-level horizontal overflow and the console reported zero warnings/errors. The isolated 14-row QA tenant was removed with zero rows remaining.
- Full local regression passed `375 passed, 27 skipped`; Node 24 TypeScript/Vite and npm audit gates are recorded separately after the final full gate run.

Limitations and blockers:

- Versioned bulk import of the public CN-GEO source taxonomy and expiry operations remain incomplete. The double-review workflow is implemented by the v4 gate below, but the real customer-labeled reviewer-agreement benchmark remains 0/20 and blocked.
- Four-platform same-cohort repetition remains incomplete until Kimi is securely reinjected after rotation. Consumer Web/App L3, production Yudao, production HTTPS object storage and customer publishing credentials remain external blockers.

Decision:

- The prior source-type placeholder is replaced by an auditable human-governed registry. Source authority governance remains `partial`, and AIRank remains commercial `NO-GO`.

## 2026-08-08 Source-Governed Evidence Packet Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- New customer artifacts use `airank.report-evidence-packet.v4`. Each Citation is reconciled to its exact snapshot and normalized host; the manifest carries the current source-classification revision, request hash, review time, validity and revision-record hash without copying the review-note body. Citation-support/fact conclusions additionally require final production independent-review provenance.
- Unclassified, expired, unknown-authority, prohibited-use and unresolved-host cases are counted separately and become explicit limitations. Observed answers and citations remain deliverable, but incomplete governance coverage makes `source_authority_summary_eligible=false`; the UI does not convert partial coverage into an overall authority claim.
- Alembic `20260808_0021` keeps multiple immutable packet versions for the same report/schema. A source review or expiry transition changes the packet basis and creates a new content-addressed version; identical evidence replays the existing content hash.
- Packet replay now verifies backing object availability and integrity. A missing object can only be restored from a freshly rebuilt identical canonical payload with the same SHA-256 and emits `report.evidence_packet_object_restored`; a corrupt object fails closed with `EVIDENCE_INTEGRITY_FAILED`.
- Real MySQL exercised 6 valid API samples, 6 citations, 2 normalized hosts, one effective high-authority source, one expired source and 2 unresolved citations. Browser export showed `1/2` valid authority coverage and the explicit no-overall-conclusion warning; the object was downloaded, browser-hashed and receipt-recorded. Desktop and 390px had no page-level horizontal overflow and zero warning/error logs. The isolated 55-row QA tenant was deleted and its temporary object directory moved to Trash.
- Full local regression passed `379 passed, 27 skipped`; real MySQL integration passed `25 passed, 2 skipped`; Node 24 TypeScript/Vite build passed and npm high-severity audit reported zero vulnerabilities. The absorption matrix remains `13 sources / 67 rows / 21 GEO skills`, and the core Skill evaluation remains `24/24` with zero falsely promoted Skills.

Limitations and blockers:

- HTML/PDF/Word rendering, digital signatures, a public verification CLI, versioned public taxonomy import, real customer-labeled review benchmark and expiry operations remain incomplete.
- This gate proves truthful governed JSON delivery, not four-platform same-cohort measurement, Consumer Web/App evidence, production authentication/storage or real customer uplift.

Decision:

- Source-governed customer evidence is no longer a report-integration gap. The artifact channel remains `partial`, and AIRank remains commercial `NO-GO` until the external production and measurement gates pass.

## 2026-08-08 Four-Provider API Repetition and Kimi K3 Contract Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- One confirmed blind question ran on one API collector surface with 3 isolated sessions per Provider. Qianwen, Doubao, Kimi and DeepSeek all completed 3/3: 12 tasks, 12 valid AnswerSnapshots, 12 EvidenceSnapshots, 12 successful attempts, 12 Provider request audits, 12 real request IDs and 12 exact usage events.
- All 12 valid answers did not mention the test brand. They remained in the effective denominator, producing an observed 0% mention/recommendation result rather than being deleted or relabeled as failures.
- `airank.measurement-quality.v4` passed 24/24 checks with `publishable=true`; API evidence completeness was 12/12. The quality report still lists missing Provider citations, unevaluated citation support, unregistered fact claims and unevaluated fact accuracy as explicit limitations.
- Kimi K3 now follows the official request contract: `max_completion_tokens=4096`, fixed temperature omitted, and `reasoning_effort=low`. Three repeated calls ended with `finish_reason=stop` and retained answer content, reasoning content, request IDs and exact usage.
- An HTTP-success/empty-answer response now retains its upstream raw payload, request ID, usage, finish metadata, duration and request contract as immutable failure evidence. It cannot enter the valid-sample denominator, while billable usage still enters the usage ledger.
- Alembic `20260808_0022` persists versioned manifest defaults and route-level effective request contracts. Configuration fingerprints participate in version identity, so credential rotation or request-parameter changes append history instead of overwriting an old audit join. Every request audit in the accepted batch matched a Provider manifest through its configuration fingerprint. Credential-pattern scans found zero matches in 54 tenant-scoped database tables and 687 workspace files.
- A clean Python 3.11 environment imports the API with the declared Playwright dependency; both Python 3.9 compatibility regression and Python 3.11 release-runtime regression are executed in the final gate.
- Python 3.9.6 and clean Python 3.11.15 regressions both passed `383 passed, 27 skipped`; Python 3.11 real MySQL integration passed `25 passed, 2 skipped`, including key-rotation history and failed-call usage accounting. The separate release-gate database upgraded from Alembic `0019` to `0022` successfully. Node 24.13.1 production build passed and `npm audit --audit-level=high` found zero vulnerabilities.

Limitations and blockers:

- This is Provider API evidence, not Consumer Web/App evidence. Consumer L3 remains `0/4`, and API search status is kept separate from browser screenshots and source panels.
- The accepted batch contains no Provider-native citations, so it does not prove citation support or fact accuracy. It also does not prove any intervention caused a brand-visibility change.
- The Kimi credential used for local acceptance appeared in conversation history and must be rotated before production. DeepSeek `v3.2` remains behind a model-sunset migration gate; `v4-pro` requires account quota.
- The fresh strict gate passes Python 3.11.15, Node 24.13.1, both remote `main` refs, all split test suites, the Web build, real MySQL and Alembic. It remains blocked because production API enforcement/Yudao and HTTPS S3/MinIO are unconfigured, optional Xinghe integrations are still `dev_only`, and Consumer browser L3 is `0/4` (login or captcha).
- Customer publishing credentials, real elapsed T+7/T+14/T+30 evidence and the full brand-to-customer-report browser E2E remain open.

Decision:

- The four-platform same-cohort API repetition gap is closed within its declared evidence scope. AIRank remains commercial `NO-GO` until Consumer and production delivery gates pass.

## 2026-08-08 Governed Knowledge Source Synchronization Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Customer-authorized public HTTP(S) sources can now opt into a governed synchronization policy. The scheduler creates durable, tenant-scoped jobs and runs; the worker uses DNS-pinned outbound fetching, immutable raw/visible-text objects and SHA-256 verification.
- A changed source creates a new immutable KnowledgeSource revision, marks the prior revision `stale` and makes facts that depend on the old source ineligible. An unchanged source records the check without fabricating a new revision.
- Active runs reject duplicate manual triggers. Run idempotency is scoped by tenant, project and policy. Transient network/storage failures use bounded 5s/10s retry delays and become terminal after attempt three while preserving the same run history.
- The Facts console can enable, change, pause and re-enable a policy, trigger an immediate check, and inspect status, current revision, timestamps, hashes and object evidence. The UI explicitly limits the function to customer-authorized sources and does not perform unauthorized site discovery.
- Real browser/MySQL acceptance imported `https://example.com/`, produced one `changed` v2 revision, then one `unchanged` check without v3. Desktop 1024px had no page-level horizontal overflow and the console reported zero warnings/errors. All isolated QA rows were deleted, and the two temporary evidence files were moved to a recoverable temporary directory.
- The fresh Python 3.11 regression passed `408 passed, 29 skipped`; the strict split gate passed 174 contract, 64 acceptance, 7 scheduler, 35 worker and all package suites. Real MySQL integration passed `27 passed, 2 skipped`; Web build, npm high-severity audit, Alembic offline SQL and real MySQL head `0024` passed. The absorption matrix remains `13 sources / 67 rows / 21 GEO skills`, and core Skill evaluation remains `30/30` with zero falsely promoted Skills.

Limitations and blockers:

- Source synchronization remains `partial`: retrieval is `lexical_only`; vector re-embedding, hybrid retrieval, private connectors, multi-page site ingestion and batch source operations are not yet implemented.
- The current collector only follows explicitly authorized public URLs. It does not prove that arbitrary sites may be crawled, that every dynamic page is extractable, or that private/customer systems are connected.
- Production API enforcement/Yudao, HTTPS S3/MinIO, optional Xinghe services, Consumer Web/App L3, customer publishing credentials and real elapsed T+7/T+14/T+30 evidence remain open. The strict report therefore remains `BLOCKED`.

Decision:

- The manual-only public knowledge source refresh gap is closed at the durable application, database and browser-workflow level. Knowledge synchronization remains `partial`, and AIRank remains commercial `NO-GO` until the external production, Consumer and observation gates pass.

## 2026-08-08 Independent Evidence Review and Agreement Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Alembic `20260808_0025` adds immutable evidence review cases for citation support and fact accuracy. A case records purpose, evidence-basis hash, first/second/adjudication review IDs, final label and lifecycle without overwriting the underlying decisions.
- The second reviewer must use a different authenticated account and cannot see the first reviewer's label or rationale while the case is pending. A disagreement requires a third distinct account; pending, disputed and old single-review records cannot enter customer metrics.
- `production` and `benchmark` are separate cohorts. Benchmark decisions never enter citation-support or fact-accuracy metrics. Quality reporting exposes raw agreement and multi-class Cohen's kappa; the deterministic gate requires at least 20 completed independent pairs and kappa >= 0.80.
- Customer packets now use `airank.report-evidence-packet.v4`. Commercial citation/fact entries must carry a final production case, secondary/adjudicator role, verified evidence boundary and immutable record hash; packet validation recomputes citation support and fact accuracy instead of trusting report labels.
- Full regression passed `427 passed, 30 skipped`; real MySQL integration passed `28 passed, 2 skipped`; Scheduler passed `7/7`, Worker `35/35`, the absorption matrix remained `13 sources / 67 rows / 21 GEO skills`, and 10 core Skills passed all 30 eval cases without false promotion. Node 24 production build and high-severity npm audit passed.
- Real browser QA retained nine valid not-mentioned samples, displayed the independent-review panel, 0/20 benchmark, the kappa >= 0.80 threshold and an explicit blocked state. Desktop 1024px and mobile 390x844 had no page-level overflow; console warning/error count was zero.

Limitations and blockers:

- The current project has no real customer-labeled benchmark pairs, so reviewer quality is 0/20 and kappa is not estimable. Engineering tests prove the workflow and formulas, not reviewer reliability.
- Production Yudao, HTTPS S3/MinIO, Consumer Web/App L3, customer publishing credentials, elapsed T+7/T+14/T+30 evidence, Kimi credential rotation and DeepSeek model migration remain open.

Decision:

- The missing double-review workflow is closed at contract, storage, API, metric, report and browser levels. Reviewer-quality evidence remains blocked, and AIRank remains commercial `NO-GO`.

## 2026-08-08 Project Evidence Integrity and Packet v5 Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Alembic `20260808_0026` adds immutable project evidence-integrity audits, per-entity findings and an optional audit link on report evidence packets. Historical packet rows remain readable with a null link.
- `airank.evidence-integrity.v1` verifies Answer/EvidenceSnapshot hashes and links, CitationCapture raw/text objects, exact citation-source boundaries, KnowledgeSource content objects, exact knowledge-segment boundaries, FactRevision hashes and every non-report evidence object reference. Empty projects and scopes above 10,000 entities fail closed.
- All verified and blocking findings are persisted. The deterministic evidence-state manifest excludes actor, request and wall-clock metadata, so identical evidence deduplicates while changed evidence creates a new audit basis.
- New customer artifacts use `airank.report-evidence-packet.v5`. Packet generation first runs the project audit, embeds its summary and manifest hash, and returns `409 REPORT_EVIDENCE_INTEGRITY_BLOCKED` before delivery if any entity is missing, corrupt or out of bounds. Historical v1/v2/v3/v4 packets remain read-only compatible and do not claim a v5 audit.
- Contract tests cover an empty project, tenant isolation, a valid nine-entity evidence graph, tampered answer content, deleted objects, response-schema validation and report generation blocked by a corrupted Provider raw response.
- A real MySQL project completed a browser-triggered audit with 36/36 entities verified and zero blockers. The Evidence Center displays policy, full manifest SHA-256 and entity-level blocking rows without fabricated scores. Desktop application logs were zero warning/error; a same-origin 390×844 container measured html/body width at 390px with no page-level horizontal overflow.
- The strict gate on commit `74b8c59` passed both remote refs, Python 3.11.15, Node 24.13.1, 184 contract tests, 69 acceptance tests, all package/worker/scheduler suites, 30/30 core Skill cases, the production Web build, real MySQL 28/2, offline SQL and real Alembic `0026` migration. The overall result remained `BLOCKED` on external production and Consumer requirements.

Limitations and blockers:

- The audit proves source-evidence integrity at one point in time. Deterministic rebuilding and comparison of all derived metric/report tables is not yet implemented, and large projects need partitioned audit execution rather than raising the 10,000-entity safety cap.
- The mobile container emitted one browser-tool MutationObserver instrumentation error that does not occur in the application source; layout assertions passed, but this run is not claimed as a zero-console mobile E2E.
- Production Yudao authentication, production HTTPS S3/MinIO, Consumer Web/App L3, real customer reviewer benchmark, publishing credentials, elapsed T+7/T+14/T+30 evidence, Kimi credential rotation and DeepSeek model migration remain open.

Decision:

- Project evidence integrity is now a hard customer-delivery gate rather than an informal assumption. AIRank remains commercial `NO-GO` until the external production, Consumer, human-quality and longitudinal-observation gates pass.

## 2026-08-08 Derived Metric Rebuild and Packet v6 Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- `airank.evidence-integrity.v2` preserves all v1 source checks and deterministically rebuilds every ScanRun `task_count` from its ScanTask rows.
- Retest report verification reloads the baseline and comparison runs from task, Answer/EvidenceSnapshot, Provider request-audit, citation and final production-review state. It rebuilds both v4 quality reports, comparison metrics, report SHA-256/status, ObservationWindow result and RetestRun summary instead of trusting stored report JSON.
- A source failure, metric drift, report hash/status drift, provenance mismatch or unsupported report type is persisted as a blocking entity-level finding. Packet generation returns `409 REPORT_EVIDENCE_INTEGRITY_BLOCKED`; an old report hash cannot substitute for recomputation.
- New customer artifacts use `airank.report-evidence-packet.v6` and bind the v2 audit manifest. Historical v1/v2/v3/v4/v5 packets remain read-only; v5 means a v1 source audit and does not claim derived-state rebuilding.
- Contract fixtures now create two real runs with three independent API samples each and derive their reports through the production quality/comparison code. A drift test mutates the report conclusion/hash and a ScanRun task count and proves both `report_derived_state` and `scan_run_metrics` blockers are recorded.
- Full regression passed `434 passed, 30 skipped`; real MySQL integration passed `28 passed, 2 skipped`.
- A real MySQL project completed the v2 audit with 39/39 entities verified and zero blockers. The Evidence Center identifies the source-plus-derived scope, policy and manifest without static scores; desktop and 390×844 mobile QA had no page-level overflow and zero console warnings/errors.

Limitations and blockers:

- Deterministic rebuilding currently covers ScanRun task counts and Retest reports. Other derived entity families fail closed or remain outside this gate; projects above the 10,000-entity cap still need partitioned audit execution.
- Production Yudao authentication, production HTTPS S3/MinIO, Consumer Web/App L3, real customer reviewer benchmark, customer publishing credentials, elapsed T+7/T+14/T+30 evidence, Kimi credential rotation and DeepSeek model migration remain open.

Decision:

- AIRank now proves that supported customer-report numbers match their stored raw evidence at delivery time. This closes the known Retest report-drift path, but AIRank remains commercial `NO-GO` until external production, Consumer, human-quality and longitudinal-observation gates pass.

## 2026-08-08 Offline Review Bundle and Packet v7 Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- New customer artifacts use `airank.report-evidence-packet.v7` and are stored as deterministic `application/zip` objects. Fixed members are README, canonical evidence manifest, printable HTML, blank review scorecard and SHA256SUMS; ZIP order, timestamp, permissions and storage mode are deterministic.
- The manifest includes the complete derived report source record but still excludes raw answer bodies and human note bodies. The offline verifier invokes the production packet builder to recalculate quality gates, metrics, evidence indexes, source governance, review hashes, packet basis and the entire ZIP.
- Verification requires the external `content_sha256` returned by AIRank or its download receipt. A missing anchor, archive/member tamper, duplicate JSON key, non-standard JSON number, decompression limit breach or deterministic-rebuild mismatch fails closed. Internal checksums are explicitly not presented as a digital signature.
- The formal CSV contains five weighted review dimensions while score, reviewer, reviewed time, rationale and decision remain blank. The HTML repeats the non-causal/no-recommendation-guarantee boundary and is print responsive.
- Contract/package/CLI tests verify deterministic replay, external anchoring, member coverage and tamper rejection. Full regression passed `438 passed, 30 skipped`; real MySQL integration passed `28 passed, 2 skipped`; Node 24 production build and high-severity npm audit passed.
- A browser-generated real MySQL bundle contained six independent samples and six citations. The v2 source/derived audit passed 15/15 with zero blockers; packet creation returned 201, object download 200 and receipt creation 201. The stored object independently returned `verified` through the CLI. Report UI and bundled HTML had no page-level overflow at 1440px or 390×844 and no console warnings/errors.

Limitations and blockers:

- PDF/Word rendering, Ed25519 or enterprise signing, and an independently hosted public verification page are not implemented. The API/download-receipt hash is the current external anchor.
- Production Yudao authentication, production HTTPS S3/MinIO, Consumer Web/App L3, real customer reviewer benchmark, customer publishing credentials, elapsed T+7/T+14/T+30 evidence, Kimi credential rotation and DeepSeek model migration remain open.

Decision:

- AIRank now has a customer-readable, offline-rebuildable evidence deliverable rather than a machine-only JSON download. It remains commercial `NO-GO` until external production, Consumer, human-quality, signing and longitudinal-observation gates pass.

## 2026-08-08 Provider-Native Citation v2 Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- `airank.provider-native-citation.v2` uses an explicit Provider-structure allowlist. Qianwen `search_info`, Responses `web_search_call.action.sources`, message/content annotations and explicit top-level citation structures are accepted; URLs found only in answer text, debug fields or unrelated nested payloads are rejected.
- Each accepted Citation retains its Provider-native type, exact raw-response JSON path and optional native source ID. `airank.provider-search-evidence.v1` separately distinguishes not requested, explicit tool execution, explicit usage, explicit no-search and requested-but-unverifiable states.
- Route request kind is now part of manifest/configuration fingerprint, route status, effective request contract and sample/request audit metadata. The supported public values are `chat_completions`, `chat_completions_search` and `responses_web_search`; invalid route values fail closed.
- A versioned seven-case benchmark covers Qianwen search info, Responses action sources, response/chat annotations, unrelated URL rejection, search-not-requested state, invalid URL rejection and deterministic deduplication. All 7/7 cases pass and the release-readiness runner executes the benchmark.
- A real Qianwen `responses_web_search` batch used one confirmed blind Prompt and three isolated sessions. All 3/3 samples were valid, all three normal not-mentioned answers stayed in the denominator, and the immutable Citation counts were 135, 90 and 135. Each sample retained a unique Provider request ID, parser version, explicit-tool-call search evidence and exact source paths. `airank.measurement-quality.v4` was publishable with 100% citation recall in this declared API scope.
- The Evidence Center renders the first 20 citations by default, can expand the complete 135-source list, and exposes request kind, search evidence, parser version and raw source path. Desktop 1543px and mobile 390x844 had no page-level horizontal overflow; the console reported zero warnings/errors.

Limitations and blockers:

- Provider selection is not Citation support. No source-page/claim independent human review was completed for this batch, so support rate and fact accuracy remain unevaluated.
- This real native-citation proof currently covers Qianwen Responses only. Doubao, Kimi and DeepSeek still need official-structure fixtures and real repeated source-bearing samples before their native citation capability can be promoted.
- API evidence does not satisfy Consumer Web/App evidence. Consumer L3 remains blocked by login/captcha, and production Yudao, HTTPS object storage, customer publishing credentials, real reviewer benchmark, Kimi credential rotation, DeepSeek model migration and elapsed T+7/T+14/T+30 evidence remain open.

Decision:

- AIRank can now prove where a Qianwen API Citation came from without scanning arbitrary URLs or claiming that source supports the answer. The capability remains `partial`, and AIRank remains commercial `NO-GO`.

## 2026-08-08 Bounded Citation Source Batch Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- A snapshot-scoped batch endpoint accepts 1–50 explicit unique Citation IDs. Before creating any job, it verifies the tenant/snapshot and validates every source URL; one invalid or foreign Citation fails the batch before any capture is queued.
- Batch context is bound into each request hash. Deterministic child idempotency keys make a partial infrastructure interruption replay-safe; same key/same payload returns the original captures, while same key/different Citation IDs fails with `IDEMPOTENCY_CONFLICT`.
- A latest-by-snapshot endpoint returns only the newest capture summary per Citation with source segments explicitly unloaded. The Evidence Center replaces per-Citation list loading with one summary call, queues at most 20 pending/failed/blocked sources per click, shows completed/active/retryable counts and loads a full capture only when its details panel opens.
- Real MySQL and Worker acceptance used an isolated 21-Citation snapshot. Initial drill-down issued one latest-summary GET; batch submission issued one POST plus one refresh; 20/20 jobs completed with content hashes and `source_page_dns_pinned`, leaving the 21st Citation pending by design. Opening one completed item then issued exactly one capture-detail GET.
- Desktop 1543px and mobile 390x844 had no page-level horizontal overflow; browser console output was 0 errors and 0 warnings. The isolated QA tenant was removed from 13 tables (130 rows total), its project count returned to zero, and two temporary object files were deleted.
- Full local regression passed `446 passed, 30 skipped`; real MySQL integration passed `28 passed, 2 skipped`; the Node 24 TypeScript/Vite build and the 13-source / 67-row / 21-Skill absorption matrix passed.

Limitations and blockers:

- A completed source capture proves that AIRank stored a content-addressed page and exact text boundaries. It does not prove that the page supports any answer Claim; independent production review and the real 20-case reviewer-quality benchmark remain required.
- The current multi-source real proof is Qianwen API evidence. Doubao, Kimi and DeepSeek native-source contracts, Consumer Web/App L3, production Yudao, HTTPS S3/MinIO, Kimi key rotation, DeepSeek model migration, customer publishing credentials and elapsed T+7/T+14/T+30 evidence remain open.

Decision:

- AIRank can safely prepare large Provider source sets for governed review without N+1 loading or false support claims. The overall product remains commercial `NO-GO` until the external production, Consumer, human-quality and longitudinal-observation gates pass.

## 2026-08-08 Exact Citation Claim Binding Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Citation review no longer offers whole-answer registration as its only path. A reviewer may select text directly inside the immutable answer; the browser maps that DOM Range to exact answer offsets and rejects selections outside the answer. Pasted text must occur exactly once or the reviewer must use direct selection.
- After registration, the source-review workbench exposes an explicit current-Claim selector. Every source-segment `supports`, `contradicts` or `insufficient` decision resolves that selected ID instead of silently using the first Claim in the response array.
- Real browser/MySQL acceptance created two Claims at boundaries 0–29 and 29–54, selected the second Claim, captured one real source page and submitted a production `insufficient` primary decision. Direct database verification proved the review case referenced the second Claim, retained the trusted session reviewer and remained `awaiting_secondary`.
- Desktop 1543px and mobile 390x844 had no page-level horizontal overflow and the browser console reported zero warnings/errors. The isolated tenant was deleted from 17 tables (20 rows), its project count returned to zero, and two temporary object files were deleted.
- The strict gate on clean commit `c0b0b0c` passed both remote `main` refs, Python 3.11.15, Node 24.14.0, 187 contract tests, 75 acceptance tests, all package/worker/scheduler suites, 7/7 citation parser cases, 30/30 core Skill cases, the production Web build, real MySQL 28/2, offline SQL and real Alembic `0026`. The overall result correctly remained `BLOCKED` on external production and Consumer requirements.

Limitations and blockers:

- This verifies precise Claim selection and evidence binding, not reviewer agreement or Citation Support. The customer benchmark remains 0/20 and no single primary decision enters a customer metric.
- Bulk Claim navigation, reviewer assignment/SLAs, Consumer Web/App L3 and production infrastructure remain incomplete.

Decision:

- AIRank no longer risks applying a source decision to the first or whole-answer Claim by UI default. Commercial status remains `NO-GO` until independent reviewer quality and external production gates pass.

## 2026-08-08 Project Reviewer Inbox Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Evidence Center now loads an actor-specific project-wide independent-review inbox instead of requiring reviewers to open every sample before discovering work. Only cases whose server-computed `next_action` is `submit_secondary` or `adjudicate` appear as actionable.
- The inbox does not expose a peer's unfinished label or rationale and does not allow an evidence-free quick decision. Reviewers must open the immutable sample, exact Claim and source context before using the existing blind review form.
- Real MySQL/browser acceptance created one benchmark primary case, signed in as a different reviewer and received one project task with `current_actor_role=null`, `next_action=submit_secondary` and `visible_decisions=[]`. Opening it loaded the immutable answer, exact 0–46 Claim and sample-level second-review form.
- Desktop 1543px and mobile 390x844 had no page-level overflow; a fresh authenticated page reported zero console warnings/errors. Cleanup deleted 15 isolated rows across 14 tables and left zero tenant rows.
- The strict gate on clean commit `602ec00` passed both remote `main` refs, Python 3.11.15, Node 24.14.0, 187 contract tests, 75 acceptance tests, every package/worker/scheduler suite, 7/7 citation parser cases, 30/30 core Skill cases, the production Web build, real MySQL 28/2, offline SQL and real Alembic `0026`. External production and Consumer requirements correctly kept the overall result `BLOCKED`.

Limitations and blockers:

- The inbox currently reads the existing whole-project case set and renders at most 12 actionable items at once. Server-side pagination, persistent assignment, reviewer-group routing, SLA/escalation and customer-team sampling remain `partial`.
- The real customer benchmark is still 0/20. This workflow makes collection operable but cannot manufacture independent labels or kappa.

Decision:

- Review work is now discoverable without weakening blind review, but AIRank remains commercial `NO-GO` until reviewer quality, production infrastructure, Consumer collection and longitudinal evidence pass their gates.

## 2026-08-09 Reviewer Inbox Cursor Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- The project reviewer inbox now has its own versioned response contract and an opaque seek cursor. MySQL filters to actor-actionable `awaiting_secondary` and `disputed` cases, excludes every case in which the current trusted actor already made either a citation or fact decision, and caps pages at 50 rows.
- Ordering is deterministic: disputed adjudications first, then oldest creation time and case ID. The cursor carries only the versioned ordering anchor; malformed or non-canonical Base64 input fails with `422 EVIDENCE_REVIEW_CURSOR_INVALID`.
- The full project case endpoint remains unpaginated for quality statistics and Cohen's kappa. Pagination therefore does not change benchmark denominators or hide completed cases from the measurement gate.
- Isolated real MySQL acceptance created 14 actor-actionable benchmark cases: 2 adjudications and 12 secondary reviews. Page one returned 12, page two returned 2, all 14 IDs were unique, the first two were disputed, and no peer decision was visible.
- Real browser acceptance loaded 12 then 14 unique cards through two HTTP 200 requests, opened the immutable answer and exact Claim, and exposed the existing evidence-bound adjudication controls. A React commit-timing defect that previously expanded the sample without scrolling to detail was fixed and reverified.
- Desktop 1543px and mobile 390x844 had no page-level horizontal overflow; the clean authenticated page reported zero console warnings/errors. Cleanup deleted 83 isolated rows across 14 tables, left zero tenant rows, and created no temporary object directory.
- The strict gate on clean commit `a63a192` passed both remote `main` refs, Python 3.11.15, Node 24.14.0, 188 contract tests, 75 acceptance tests, every package/worker/scheduler suite, 7/7 citation parser cases, 30/30 core Skill cases, the production Web build, real MySQL 28/2, offline SQL and real Alembic `0026`. External production and Consumer requirements correctly kept the overall result `BLOCKED`.

Limitations and blockers:

- This is dynamic queue discovery, not persistent ownership. Reviewer assignment, team routing, SLA/escalation, workload locking and sampling policy remain `partial`.
- The real customer benchmark remains 0/20 and kappa remains unavailable. Engineering fixtures and the 14 QA cases do not satisfy the customer labeling gate.

Decision:

- Large reviewer queues can now be traversed without weakening blind review or distorting quality statistics. AIRank remains commercial `NO-GO` until reviewer quality, production infrastructure, Consumer collection and longitudinal evidence pass their gates.

## 2026-08-09 Reviewer Assignment Lease Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- Alembic `20260809_0027` adds tenant/project-scoped reviewer assignments and append-only assignment events. The schema reached 69 AIRank tables in real MySQL; a generated active-slot unique key and case-row locking ensure at most one active owner for each case/reviewer role.
- Claim is idempotent for the same trusted actor and conflicts for another active owner. Heartbeat, release and expiry takeover use optimistic versions; heartbeat extends the lease without resetting the original secondary/adjudication SLA. Direct decision submission atomically auto-claims an unowned case and completes the assignment.
- Public assignment responses expose ownership state, lease/SLA timestamps and version but never `assigned_to`. The actor-specific inbox excludes work held by another active reviewer, includes expired work for takeover, and reports assigned-to-me, unassigned and overdue counts without changing full-project agreement or kappa denominators.
- Real MySQL used two concurrent threads against the same case: one claim succeeded and one returned `EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT`. The same test verified stable `due_at` across heartbeat, release, forced expiry, persisted expiry event, takeover, automatic completion and adjudicator assignment.
- Real browser acceptance signed in as a secondary reviewer and exercised unassigned/overdue display, claim, peer-account invisibility, heartbeat, release, reclaim and evidence-bound drill-down. The detail showed the immutable answer, exact Claim, source text and second-review form. Public network responses contained no assignee identity.
- Desktop 1543px and mobile 390×844 had no page-level horizontal overflow; all three assignment controls fit the mobile viewport. After completing the QA fixture, the fresh authenticated page had zero console warnings/errors. The isolated tenant was removed from all 61 tenant-scoped tables with zero rows remaining.
- Full local regression passed `449 passed, 30 skipped`; contracts passed `189`; acceptance passed `76`; real MySQL integration passed `28 passed, 2 skipped`; the Node 24 production build passed.
- The strict gate on clean commit `08b38f9` passed both remote `main` refs, all split suites, Web build, real MySQL, offline SQL and real Alembic `0027`. Its overall result remained correctly `BLOCKED` only on the declared production auth/storage, optional external capability and Consumer browser L3 requirements.

Limitations and blockers:

- Persistent ownership is individual actor routing, not a production reviewer-team dispatcher. Yudao group/permission routing, on-call rotation, workload balancing and automated SLA escalation notifications are not implemented.
- The real customer benchmark remains 0/20 and Cohen's kappa is still unavailable. Concurrency and browser fixtures prove engineering behavior only; they do not establish reviewer quality.
- Production Yudao authentication, HTTPS S3/MinIO, Consumer Web/App L3, Kimi credential rotation, DeepSeek model migration, customer publishing credentials and elapsed T+7/T+14/T+30 evidence remain open.

Decision:

- AIRank now prevents duplicate reviewer ownership and preserves a complete assignment/SLA audit trail without weakening blind review. The capability remains `partial`, and AIRank remains commercial `NO-GO` until reviewer-quality and external production gates pass.

## 2026-08-09 Reviewer SLA Escalation Outbox Gate

Release Gate: PARTIAL / COMMERCIAL NO-GO

Passed:

- The shared Scheduler now scans tenant/project-scoped `awaiting_secondary` and `disputed` cases and persists versioned `evidence_review.sla_overdue.v1` events to the existing durable Outbox. Stable IDs make replay idempotent; scope safety caps the scan at 10,000 actionable cases and dispatch at 500 events per tick.
- Before insertion, the Scheduler locks and reloads the case and active assignment, then recomputes reviewer role, due time and event ID. A case completed or changed after the initial scan produces no stale event.
- Event payloads declare `airank.evidence-review-sla-escalation.v1` and `delivery_claim=outbox_pending_not_delivered`. Public list responses exclude assignee and assignment identity and always return `external_delivery_verified=false`.
- Evidence Center shows real persisted counts and event cards. It distinguishes dynamic overdue work from Scheduler-persisted escalation and explains that neither `pending` nor `published` proves delivery through Feishu, email or SMS.
- Contract, scheduler and acceptance regression passed 17 targeted tests. The real MySQL independent-review integration passed with one new escalation, idempotent replay and the existing claim/lease/release/expiry/takeover/adjudication chain intact.
- Full regression passed `454 passed, 30 skipped`; contracts passed `190`, acceptance passed `77`, scheduler passed `10`, real MySQL integration passed `28 passed, 2 skipped`, the 13-source / 67-row / 21-Skill absorption matrix passed, and the Node 24 production build plus high-severity npm audit passed.
- The strict release runner on clean commit `1e0426e` passed both remote `main` refs, runtime floors, all split suites, Web build, real MySQL, offline SQL and real Alembic `0027`. The overall result remained correctly `BLOCKED` on production auth/storage, optional external capabilities and Consumer browser readiness `0/4`.
- Isolated real MySQL/browser acceptance displayed one overdue secondary-review task, one persisted pending event and zero externally verified deliveries. The public response contained no `assigned_to` or `assignment_id`; evidence drill-down still loaded the immutable answer, exact Claim, source text and second-review form. Desktop and mobile had no page-level horizontal overflow and console warning/error count was zero. All 61 tenant-scoped tables were cleaned back to zero QA rows.

Limitations and blockers:

- No external notification Consumer or delivery-receipt contract is implemented. `published` currently means only that an Outbox publisher processed the event, not that a person or channel received it.
- Reviewer-team routing, Yudao group/permission mapping, escalation recipients, repeat escalation levels, on-call rotation and workload balancing remain incomplete. Failed/canceled escalation operations need a governed retry/recovery workflow.
- The real customer review benchmark remains 0/20 and Cohen's kappa remains unavailable. Persistent SLA operations do not establish reviewer quality.
- Production Yudao authentication, HTTPS S3/MinIO, Consumer Web/App L3, Kimi credential rotation, DeepSeek model migration, customer publishing credentials and elapsed T+7/T+14/T+30 evidence remain open.

Decision:

- AIRank can now prove that an overdue independent-review task created one durable operations event without claiming anyone was notified. The capability remains `partial`, and AIRank remains commercial `NO-GO` until external delivery, reviewer-team routing, customer quality and production gates pass.

## Reviewer team and role routing gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0028` adds tenant/project reviewer teams, role memberships and secondary/adjudicator routes. Real MySQL is at head with 72 AIRank tables; offline SQL and real migration both pass.
- Manual memberships remain explicitly external-unverified. The API exposes team/role capacity and route readiness but does not claim Yudao group synchronization.
- A project with no route is explicitly `unrestricted_legacy`. Once any route is configured, an unconfigured role, inactive/empty team, non-member actor or exhausted member capacity fails closed. Both roles must be ready before the project reports `team_routed`.
- Inbox filtering and assignment creation share the same database eligibility rule. Assignment creation locks the member row before counting active work, while an existing assignment owner may still finish their leased task at capacity.
- SLA escalation persists the resolved team, route version, eligible-recipient count and external-sync state in the same Outbox transaction. Member user IDs and assignee identity are absent; `external_delivery_verified` remains false.
- Real MySQL verified a non-member receives zero actionable cases and a 403 claim denial, members retain unique concurrent ownership, and the escalation route resolves two recipients. Contract/acceptance/scheduler suites and the full default suite pass.
- Real browser acceptance created one team, secondary/adjudicator memberships and both routes through the public API. Desktop and 390×844 mobile views showed `team_routed`, two ready routes, no page overflow and console `0 error / 0 warning`. All QA rows and their audit events were then deleted from the demo project.
- The clean `f70ceeb` strict gate passed both remote `main` refs, Python 3.11.15, Node 24.14.0, 195 contract, 6 crawler-lite, 78 acceptance, 12 scheduler, 35 worker, 48 evidence, 23 outbound-security and 26 Provider Gateway tests, 7/7 citation parser cases, 30/30 core Skill cases, the production Web build, real MySQL `28 passed, 2 skipped`, offline SQL and real Alembic `0028`.

### Still blocked

- Yudao group and membership synchronization is not implemented; manual member binding is not external identity proof.
- There is no external notification Consumer, channel receipt, repeated escalation level, on-call rotation or automatic workload balancing. Outbox `published` is not delivery.
- The real customer-labeled reviewer benchmark remains 0/20, so kappa is unavailable and commercial reviewer reliability is not established.

### Decision

- Internal project reviewer routing is now a durable, capacity-bounded engineering capability. AIRank remains commercial `NO-GO` until external delivery, customer reviewer quality and the existing production infrastructure/Consumer gates pass.

## Yudao reviewer-directory synchronization gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0029` adds role-scoped Yudao directory bindings and immutable synchronization runs. Bindings retain the external department ID, interval, next-due time and configuration fingerprint; runs retain response SHA-256 and member change counts.
- The adapter reads the configured Yudao department and enabled-user endpoints, returns only reviewer identity fields required for routing, fails closed, and never puts credentials in job payloads, API responses or synchronization records.
- The shared Scheduler emits tenant/project-scoped `airank.reviewer-directory-sync.v1` jobs. The Worker rechecks the binding ID, version, team and reviewer role before network access. Unchanged source snapshots do not create new member versions; missing source users are disabled.
- Contract, adapter, API, Scheduler and Worker tests pass. Real MySQL exercised manual and scheduled synchronization through a protocol-faithful directory fixture, then proved a second unchanged snapshot produced zero member updates and no version churn.
- Evidence Center exposes binding configuration, immediate synchronization and immutable run hashes/counts while stating that credentials are server-side only. The current project correctly shows no production binding instead of claiming Yudao verification.

### Still blocked

- No production Yudao reviewer-directory credentials or customer department were supplied. The fixture proves AIRank behavior, not that a production member currently belongs to a real customer group.
- Production Yudao login/permission-info remains a separate release requirement from directory synchronization.

### Decision

- The Yudao directory integration is implemented and testable, but external membership proof remains `blocked` until a production customer directory is synchronized and audited.

## Review-notification delivery receipt gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0030` adds durable notification deliveries and append-only per-attempt receipts for SLA escalation Outbox events.
- The notification Consumer accepts only a server-injected public HTTPS Webhook, uses DNS-pinned outbound transport without redirects, and retries only 408/425/429/5xx with bounded backoff. Bearer credentials are never persisted.
- Each attempt stores request/response SHA-256, response status, connected IP, endpoint host and upstream receipt ID. An Outbox event becomes `published` only after a 2xx response and a successful receipt are committed; the API returns `external_delivery_verified=true` only under the same condition.
- Unit coverage proves retry-to-success, terminal failure and missing-configuration fail-closed behavior. Real MySQL plus a protocol-faithful HTTP 202 fixture proves the receipt is visible through the escalation API and that the injected secret is absent from persisted delivery data.
- Evidence Center explains the distinction between pending Outbox work and verified external delivery. The live project shows no verified delivery because no customer Webhook is configured. Desktop and mobile have no page-level horizontal overflow; the browser console has zero warnings/errors.

### Still blocked

- No customer-owned HTTPS Webhook or downstream channel account was supplied, so real external delivery and recipient receipt remain unverified.
- Repeated escalation levels, on-call rotation and automatic workload balancing remain `partial`.
- The real customer reviewer benchmark remains 0/20, Cohen's kappa is unavailable, and engineering fixtures do not establish reviewer quality.

### Decision

- AIRank now has truthful delivery semantics and an immutable channel-attempt audit trail. It remains commercial `NO-GO` until a customer channel, production reviewer identity, reviewer-quality benchmark and existing infrastructure/Consumer gates pass.

## Reviewer sync and notification strict release gate (2026-08-09)

### Passed on clean synchronized commit

- Clean commit `ef84cf2` was present on both GitHub and Gitee `main` and `codex/evidence-productization`; worktree, diff and tracked-runtime-artifact checks passed before the report was generated.
- Production runtime floors passed with Python 3.11.15 and Node 24.14.0.
- Tests passed: contracts 197, crawler-lite 6, acceptance 78, Scheduler 15, standalone Worker 41, score 16, evidence 48, outbound-security 23, Provider Gateway 26 and Xinghe adapter 10. Provider-native citation cases passed 7/7 and the 10 core Skills passed 30/30 evaluation cases.
- The production Web build passed. Real MySQL integration passed `28 passed, 2 skipped`; offline migration SQL and real Alembic head `20260809_0030` passed.
- The first strict run exposed that standalone Worker tests did not load the Xinghe adapter path. This was corrected in `apps/worker/pytest.ini` and runtime examples, committed independently, synchronized to both remotes, and then reverified as 41/41 passing. The failed run is not presented as a release pass.

### External blockers retained by the gate

- Production API authentication is not configured as required Yudao auth, and production HTTPS S3/MinIO is not configured.
- Optional external Crawler, KB, creator-marketing, workflow-runner and Hermes capabilities remain `dev_only` under the strict optional-capability policy.
- Consumer browser generation remains 0/4: Doubao and Kimi require login; Qianwen and DeepSeek require human verification/captcha. API evidence is not substituted for Consumer Web/App evidence.
- No production Yudao reviewer directory or customer HTTPS notification Webhook was supplied. Kimi credential rotation, DeepSeek model migration, customer publishing credentials, the real 0/20 reviewer benchmark and elapsed T+7/T+14/T+30 evidence remain open.

### Decision

- The current engineering slice passes every executable strict check and closes the standalone Worker packaging defect. AIRank remains commercial `NO-GO` because the remaining failed gates require production/customer identities, infrastructure, channel endpoints or elapsed evidence.

## Evidence-backed content-gap derivation gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0031` adds provenance fields to `airank_content_gaps` and an immutable, idempotent derivation-run ledger. The real database is at head with 77 AIRank tables; offline SQL and real migration pass.
- `airank.evidence-gap.v2` accepts only a completed scan whose recomputed `airank.measurement-quality.v4` report is publishable. Each question/provider/surface group must contain every expected sample index, independent sessions, immutable answer/raw hashes, and only valid `not_mentioned` samples.
- The result freezes the quality-report hash, canonical evidence-basis hash, AnswerSnapshot/EvidenceSnapshot/Citation identifiers, sample counts, policy version and trusted actor. Normal unmentioned samples remain in the measurement denominator; skipped groups are not deleted.
- Legacy gaps without contract/evidence hashes remain auditable but are excluded from asset actions. A governed gap without approved FactAtom evidence appears as `待补事实`, not as generated content.
- Contract/unit/acceptance tests cover deterministic derivation, mentioned/reused-session rejection, authenticated actor override, JSON Schema validation and legacy-gap exclusion. Real MySQL proves one 3-sample unmentioned group creates one gap, a mentioned group creates zero, and replay creates no duplicate.
- Browser acceptance proves a quality-blocked run returns 409 without changing the one existing gap; the quality-passed Doubao API run idempotently replays and drills down to 3 AnswerSnapshots, 3 EvidenceSnapshots and both 64-character hashes. Mobile has no page overflow and console warning/error counts are zero.

### Still blocked

- The current gap policy covers only stable brand non-mention. Citation-support gaps, fact-conflict/staleness gaps, page-audit findings and a cross-domain opportunity priority model are not yet orchestrated.
- The verified gap has zero approved FactAtoms and therefore cannot generate or publish content. This is intentional fail-closed behavior, not a completed intervention.
- Production Yudao authentication/directory, HTTPS object storage, customer notification and publishing endpoints, Consumer Web/App evidence, reviewer benchmark 0/20, Kimi rotation, DeepSeek migration and elapsed T+7/T+14/T+30 customer evidence remain open.

### Decision

- The evidence-to-action boundary is now truthful and auditable, but AIRank remains commercial `NO-GO` until the existing external and customer-evidence gates pass.

## Governed fact-acquisition gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0032` adds durable fact-acquisition tasks and hash-chained append-only events. A task freezes the v2 gap evidence hash, quality-report hash, questions, Provider, collection surface, authority policy, actor, version and idempotency request.
- Only `airank.evidence-gap.v2` gaps with complete immutable hashes and no existing FactAtom evidence can create a task. Legacy gaps and already-evidenced gaps fail closed.
- Binding a FactRevision validates project scope, source existence, active validity, official or verified-third-party authority, source-content integrity hash, exact fact-text boundary, human approval, current revision, public/redacted disclosure and absence of open conflicts.
- Proposed or otherwise ineligible facts cannot set `generation_allowed`; approved evidence moves both the task and source gap to `ready_for_intervention`. This state does not create content or claim publication/model recommendation.
- Contract and acceptance tests cover actor trust, strict JSON schemas, legacy rejection, pending-versus-approved state transitions, idempotent replay, event count/hash and exact-boundary/hash rejection. Real MySQL completes gap → task → official source → reviewed FactRevision → resolved task, and the asset state changes from `待补事实` to `待生成` only after the evidence gate passes.
- The live browser project intentionally has no approved facts: it displays one task as `待提议事实`, zero sources/revisions/approved facts and a disabled binding action. The 390×844 requested viewport is rendered at the in-app browser's 312×675 content viewport without page overflow; console warnings/errors are zero.
- The strict release gate was rerun on the clean, dual-remote-synchronized feature commit `44c7ceb`. Contracts 205, crawler-lite 6, acceptance 81, Scheduler 15, standalone Worker 41, score 16, evidence 48, outbound-security 23, Provider Gateway 26 and Xinghe adapter 10 all pass; Provider-native citations pass 7/7, core Skills pass 30/30, the production Web build passes, real MySQL passes `28 passed, 2 skipped`, and both offline SQL plus real Alembic head `20260809_0032` pass.

### Still blocked

- The live customer-like project still has no supplied enterprise source or approved fact, so no intervention content was generated from its real gap.
- Fact-acquisition assignment ownership, SLA/escalation and automatic routing to knowledge owners are not yet implemented.
- Citation-support, fact-staleness/conflict and page-audit findings are not yet normalized into the same cross-domain opportunity model.
- All previously recorded production infrastructure, identity, Consumer Web/App, customer publishing, reviewer benchmark, credential migration and elapsed retest blockers remain open.
- The strict report therefore remains `BLOCKED`: the API-auth configuration check passes under explicit `required`/`yudao` settings, but the real Yudao permission endpoint is absent; object storage is still local, optional Xinghe capabilities are `dev_only`, and Consumer browser L3 generation is 0/4 because login or captcha verification blocks all four providers. Real Provider API success is not substituted for these missing production/Consumer proofs.

### Decision

- AIRank now has a truthful gap-to-fact handoff with immutable audit evidence. The engineering slice is complete, but the product remains commercial `NO-GO`; no content or recommendation outcome is claimed.

## Cross-domain intervention opportunity gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0033` adds immutable full-project derivation runs and per-opportunity snapshots under `airank.intervention-opportunity.v1` and `airank.cross-domain-opportunity-policy.v1`.
- The derivation accepts four governed sources: quality-gated `airank.evidence-gap.v2` brand visibility gaps; Provider Citation/Claim evidence with source-page and independent final-review requirements for commercial support labels; open FactConflict plus stale/expired/expiring KnowledgeSource and FactRevision records; and only the latest completed content-hashed page audit per URL.
- Every result freezes source object references, source-evidence SHA-256, snapshot SHA-256, evidence level, intervention gate and the exact severity/evidence/urgency score factors. The resulting priority score is an action-ordering value, never a recommendation rate, brand score or growth forecast.
- Adjacent immutable runs distinguish new, persisting and cleared IDs. “Cleared” is exposed as “not observed in this run” and never auto-resolves the source object. For page findings, the stable ID is URL + rule based: a later failed audit keeps the ID while changing the evidence hash; a later clean audit removes it from the current snapshot.
- Brand opportunities remain `blocked_evidence` until the source evidence gap is `ready_for_intervention`; derivation does not generate content. Citation support labels enter `ready_for_action` only after a production review case ends in independent `agreed/adjudicated` source-page evidence.
- Contract/acceptance tests validate strict schemas, trusted actor override, explicit non-recommendation semantics and all four sources. Full local regression passes `493 passed, 31 skipped`; real MySQL passes `29 passed, 2 skipped`, including four-source creation, three immutable generations, stable page-rule persistence, clean-page exit, historical queries, idempotent replay and exact cleanup. Node 24.14.0 production build and production high-severity npm audit both pass.
- The live browser project derives one real Doubao repeated non-mention opportunity from its existing governed gap. Repeated generation shows `0 new / 1 persisting / 0 not observed`, zero actionable and one evidence-blocked item; the action score is labeled “not recommendation rate”. The requested 390×844 viewport renders at the in-app browser's 312×675 content area with no page-level horizontal overflow and zero console warnings/errors.
- The strict gate was executed on clean commit `89a0871`, with both GitHub/Gitee `main` refs matching. Runtime versions, 208 contract tests, 6 crawler-lite tests, 83 acceptance tests, 15 Scheduler tests, 41 standalone Worker tests, 16 score tests, 48 evidence tests, 23 outbound-security tests, 26 Provider Gateway tests, 10 Xinghe adapter tests, 7/7 native-citation cases, 30/30 core Skill cases, Web production build, real MySQL `29 passed, 2 skipped`, offline SQL and real Alembic head `20260809_0033` all pass.

### Still blocked

- The live project still has no approved enterprise FactRevision, so the brand opportunity cannot become content-ready. No intervention content, external publication or recommendation outcome was produced.
- Opportunity self-claim, due dates, versioned waiver and evidence-backed “not observed” closure now exist. Yudao team routing, capacity-aware assignment, automatic SLA escalation/notification, budget/effort estimates and dependency ordering remain open. Citation-zero observations are deliberately not auto-interpreted as support gaps without a governed lifecycle.
- Production Yudao authentication/directory, HTTPS object storage, customer notification and publishing endpoints, Consumer Web/App evidence, reviewer benchmark 0/20, Kimi credential rotation, DeepSeek model migration and elapsed T+7/T+14/T+30 customer evidence remain open.
- The strict report remains `BLOCKED`: local filesystem storage is not production S3/MinIO; real Yudao permission endpoints are absent; optional Crawler/KB/content/workflow/Hermes capabilities are `dev_only`; Consumer browser L3 remains 0/4 because Doubao/Kimi require login and Qianwen/DeepSeek require human verification. Provider API success is not substituted for Consumer evidence.

### Decision

- The cross-domain diagnosis slice is evidence-backed and internally deliverable, but AIRank remains commercial `NO-GO`. The opportunity board is an auditable action queue, not proof that any model will recommend the brand.

## Governed opportunity action gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0034` adds one current action projection per stable opportunity plus append-only, previous-hash-linked action events under `airank.opportunity-action.v1`.
- Actions can only be created from the latest complete immutable opportunity snapshot. They freeze the source and latest snapshot/run IDs, snapshot/evidence hashes, action type, owner, severity-derived due date, version and idempotent creation request.
- Claiming uses the authenticated actor and optimistic version. Another actor cannot release, refresh, waive or complete the owner's action. An `evidence_blocked` action remains blocked after claim; only a newer `ready_for_action` snapshot can refresh it into open/in-progress.
- A previous non-empty baseline may now be followed by a complete zero-opportunity derivation, so an all-clear observation is recorded rather than rejected as missing input. The first ever derivation still fails closed when no governed source evidence exists.
- `verified_not_observed` requires the owner's explicit acknowledgement and a newer latest complete derivation whose opportunity manifest is internally consistent and does not contain the stable opportunity. A waiver requires an owner and a substantive reason. Both keep `effect_claim_allowed=false`; neither is a recommendation, growth or permanent-resolution claim.
- Contract/acceptance tests cover trusted actors, strict request schemas, final-state acknowledgement, SLA derivation, zero-opportunity snapshots and non-effect semantics. Full local regression passes `498 passed, 32 skipped`; real MySQL passes `30 passed, 2 skipped`, including create/claim, cross-owner rejection, evidence refresh, zero-opportunity verification and a four-event hash chain. Node 24 production build passes.
- The live browser project creates and claims the real evidence-blocked Doubao non-mention opportunity. The board shows the authenticated owner, 30-day SLA, two events/version 2 and “effect claim forbidden”; it does not expose a completion button while the opportunity persists. The requested 390×844 viewport renders at 312×675 with no page-level horizontal overflow and zero console warnings/errors.
- The strict gate on feature commit `7cd8c1a` passes every executable engineering check: 211 contract, 6 crawler-lite, 85 acceptance, 15 Scheduler, 41 Worker, 16 score, 48 evidence, 23 outbound-security, 26 Provider Gateway and 10 Xinghe adapter tests; 7/7 native-citation cases; 30/30 core Skill cases; the Node 24 production Web build; real MySQL `30 passed, 2 skipped`; offline SQL; and real Alembic head `20260809_0034`.

### Still blocked

- Opportunity actions do not yet use Yudao team-directory routing, capacity limits or automatic SLA escalation/notification. Resource budgets, effort estimates and cross-opportunity dependency scheduling are also absent.
- The live action is intentionally evidence-blocked because the project still has no approved enterprise FactRevision. No content, publication, retest improvement or recommendation outcome was produced.
- All external production blockers from the preceding gate remain: production Yudao, HTTPS object storage, customer notification/publishing endpoints, Consumer Web/App sessions, reviewer benchmark, credential/model migration and elapsed customer observation windows.
- Under the strict external policy, the report remains `BLOCKED`: object storage is local rather than production HTTPS S3/MinIO; no real Yudao permission endpoint is configured; optional Crawler/KB/content/workflow/Hermes capabilities remain `dev_only`; and Consumer Browser L3 is `0/4` because Doubao/Kimi require login while Qianwen/DeepSeek require human verification. Provider API evidence is not substituted for Consumer evidence.

### Decision

- AIRank can now turn evidence-backed opportunities into owned, auditable work without turning task completion into a marketing outcome. This closes an internal delivery gap but does not change the commercial `NO-GO` decision.

## Opportunity action routing and SLA escalation gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0035` adds project-scoped opportunity delivery teams, members and one current route for each of the four opportunity source kinds. The action projection freezes route/team/member versions and external membership verification state; the real database is at head with 86 AIRank tables.
- With no route configuration, the existing behavior is explicitly labeled `unrestricted_legacy`. Once any route is configured, missing source routes, disabled or empty teams, non-members and owners at their active-action capacity all fail closed. Claim resolution locks the member row and counts current non-final assignments before assignment.
- Manual members remain `external_membership_verified=false`; this implementation does not claim Yudao directory verification. Admin mutations require `airank:opportunity:admin`, while authenticated project users can read routing state needed to understand why a claim is blocked.
- The Scheduler now re-locks overdue non-final actions and writes deterministic `opportunity_action.sla_overdue.v1` Outbox events. Payloads omit owner/member identity, preserve route version and recipient count, set `delivery_claim=outbox_pending_not_delivered`, and keep `effect_claim_allowed=false`.
- The existing DNS-pinned HTTPS notification Consumer accepts both reviewer and opportunity-action SLA events. Only a persisted successful 2xx channel receipt can make `external_delivery_verified=true`; a pending Outbox row is not external delivery.
- Real MySQL verifies team creation, membership, source routing, non-member rejection, authenticated claim, route/member snapshots, one idempotent overdue event, pending delivery semantics, later evidence refresh, zero-opportunity verification and exact cleanup. Default regression passes `507 passed, 32 skipped`; real MySQL passes `30 passed, 2 skipped`; focused Scheduler/Worker/API coverage passes 70 tests; Node 24 Web production build and production dependency audit pass.
- The asset workflow now reads the real routing API, shows member capacity and external-verification state, configures all four source routes, and exposes action escalation/receipt state. This new UI passed TypeScript/Vite production build; browser visual/E2E acceptance has not been rerun in this slice and remains explicitly pending.

### Still blocked

- Opportunity delivery teams do not yet synchronize from a real Yudao group. Manual members are usable for controlled internal delivery but are not production directory proof.
- No customer HTTPS notification endpoint was supplied, so the new action SLA event is proven only through durable pending Outbox state; external recipient delivery remains unverified.
- Budget, effort, dependency ordering and 30/60/90 portfolio scheduling are not yet implemented. No expected growth or recommendation uplift is generated.
- Existing production object storage, Yudao auth, optional Xinghe services, Consumer Browser L3, reviewer benchmark, customer publishing and elapsed T+7/T+14/T+30 blockers remain unchanged.

### Decision

- Team routing and capacity close another internal delivery-control gap, but AIRank remains commercial `NO-GO`. Build success, manual membership and pending escalation events are not substituted for production identity, external delivery or observed GEO outcomes.

## Opportunity execution planning and dependency gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0036` adds one current human execution plan per opportunity action, cross-action dependencies and a shared append-only plan/dependency event ledger with previous-event SHA-256. The real database is at head with 89 AIRank tables.
- Plans explicitly store `estimate_source=human_estimate`, effort hours, CNY budget, optional timezone-aware dates, assumptions, optimistic version and `outcome_forecast_allowed=false`. Portfolio effort and budget remain null until every non-final action has an approved plan.
- Dependency creation is idempotent, rejects self-dependency and in-progress targets, serializes graph mutation by locking the project's actions and rejects cycles. Duplicate edge types do not corrupt topological indegree. Final prerequisites and waived dependencies no longer block or pollute the open-action execution order.
- An unsatisfied dependency now blocks an open action from being claimed into `in_progress`, and blocks an assigned evidence-gated action from refreshing into execution. A waiver requires the current version, a substantive reason and explicit acknowledgement that no outcome claim is allowed; it appends rather than overwrites audit history.
- The asset workflow reads the real portfolio API and exposes coverage, conditional totals, dependency blockers, topological layers, plan approval, dependency creation and explicit waiver. Labels state that estimates are not invoices, spend or recommendation/growth forecasts. Node 24 TypeScript/Vite production build passes; the new planning UI has not been rerun through browser visual/E2E acceptance in this slice and remains pending.
- Contract and acceptance suites pass 219 and 89 tests. Full default regression passes `514 passed, 33 skipped`; real MySQL passes `31 passed, 2 skipped`. The real planning chain verifies no partial totals, 4h/1000 + 6h/2000 = 10h/3000 after complete approval, deterministic two-layer ordering, reverse-cycle rejection, claim blocking, audited waiver, post-waiver claim and a two-event dependency hash chain.
- The strict gate on clean, dual-remote-synchronized commit `ba628f1` passes worktree and both `main` refs, Python 3.11.15, Node 24.14.0, 219 contracts, 6 crawler-lite, 89 acceptance, 18 Scheduler, 42 standalone Worker, 16 score, 48 evidence, 23 outbound-security, 26 Provider Gateway and 10 Xinghe adapter tests, 7/7 native-citation cases, 30/30 core Skill cases, Web production build, real MySQL `31 passed, 2 skipped`, offline SQL and real Alembic `0036`. The overall result remains correctly `BLOCKED` by external production and Consumer gates.

### Still blocked

- Human estimates are not contracts, time sheets, invoices or observed spend. Calendar-aware capacity scheduling and a governed 30/60/90 portfolio view are not implemented.
- The new planning UI has production build evidence but no fresh browser click/visual evidence. It must not be described as browser-E2E complete until that separate gate runs.
- Real Yudao action-team synchronization and a customer HTTPS notification receipt remain absent. Manual team membership and pending Outbox events are not production identity or delivery proof.
- Existing production HTTPS object storage, Yudao auth, optional Xinghe services, Consumer Browser/App collection, customer publishing, reviewer benchmark, Kimi credential rotation, DeepSeek model migration and elapsed T+7/T+14/T+30 evidence blockers remain unchanged.

### Decision

- AIRank can now turn an evidence-backed opportunity queue into a constrained human execution portfolio without inventing ROI. This engineering slice is complete, but the product remains commercial `NO-GO` until the external production, browser and customer-evidence gates pass.

## Opportunity action Yudao directory gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0037` adds one optimistic-versioned Yudao department binding per opportunity delivery team and immutable directory-sync runs. The real MySQL database is at head with 91 AIRank tables.
- API, Scheduler and Worker share `airank.opportunity-action-directory-sync.v1`. Jobs freeze tenant, project, team, binding, external group and binding version but never persist directory credentials. The Worker revalidates every scope field before the upstream request, and a binding change during fetch records a failed run with zero member writes.
- Sync writes are limited to `membership_source=yudao`. Equal snapshots do not increment member versions, disappeared external members are disabled, and an existing manual member with the same user ID is preserved with `external_membership_verified=false` and reported as a manual conflict.
- The opportunity workflow now uses the real directory API for binding, immediate sync, run status, response hash and created/updated/unchanged/disabled/manual-conflict counts. The production TypeScript/Vite build passes; this new UI has not received a fresh browser click/visual run and remains explicitly pending.
- Focused contract, API, repository, Scheduler and Worker tests cover strict schemas, permissions, idempotent replay, stable member versions, manual-member preservation, binding drift and retryable failure. The exact real MySQL binding → Scheduler → Worker → Yudao protocol fixture → member provenance → audit chain passes.
- On clean, GitHub/Gitee-synchronized commit `0efb887`, the strict release gate passes 222 contract, 6 crawler-lite, 89 acceptance, 20 Scheduler, 45 standalone Worker, 16 score, 48 evidence, 23 outbound-security, 26 Provider Gateway and 10 Xinghe adapter tests; Provider-native citations pass 7/7, core Skills pass 30/30, the Node 24 production Web build passes, real MySQL passes `34 passed, 2 skipped`, and offline SQL plus real Alembic head `20260809_0037` pass. The wider default regression separately passes `524 passed, 34 skipped`; the focused real MySQL directory chain was also verified in the `33 passed, 2 skipped` integration run before the final strict gate.

### Still blocked

- No production Yudao department, permission endpoint or runtime credential was supplied. The protocol fixture proves AIRank's boundary and failure policy, not a real customer directory E2E.
- The strict report remains `BLOCKED`: runtime authentication is `disabled/dev_only`, object storage is local rather than production HTTPS S3/MinIO, and optional Crawler/KB/content/workflow/Hermes services are unconfigured `dev_only` capabilities.
- Consumer Browser L3 was deliberately not rerun in this slice. The last verified result remains 0/4: Doubao and Kimi require authenticated sessions, while Qianwen and DeepSeek require human captcha verification. Provider API success is a different evidence grade and cannot replace those missing Consumer proofs.
- Customer HTTPS notification and publishing endpoints, the 20-case reviewer benchmark, Kimi credential rotation, DeepSeek model migration and elapsed T+7/T+14/T+30 customer evidence remain open. Calendar-aware capacity and a governed 30/60/90 execution portfolio also remain unimplemented.

### Decision

- Opportunity delivery teams now have an auditable external-directory synchronization boundary without corrupting manual ownership data. This engineering slice is complete, but AIRank remains commercial `NO-GO`; no production identity, external delivery, publication or GEO outcome is claimed.

## Governed 30/60/90 capacity scheduling gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0038` adds five project-scoped tables for member capacity calendars, date exceptions, previous-hash-linked calendar events, immutable 90-day schedule runs and per-action schedule results. The real MySQL database is at head with 96 AIRank tables.
- Capacity inputs require an IANA timezone, unique ISO workdays, positive weekly hours and a substantive manual basis. Date exceptions have independent optimistic versions. Equal content replays without version growth; changed content appends a hash-linked event. Manual entries always remain `external_calendar_verified=false`.
- `airank.opportunity-capacity-schedule.v1` freezes action, approved-plan, routed-member, calendar, exception and dependency versions/hashes. It allocates human-estimated effort by available workday, detects shared-member daily over-allocation and returns 0–30, 31–60 and 61–90 windows plus explicit unplanned, missing-date, missing-owner, missing-calendar, unavailable-calendar, dependency, capacity and outside-horizon states.
- Schedule runs and items are immutable. The same `Idempotency-Key` replays the original run and cannot be reused for another request; an independent key can retain a separate run even when its source and result hashes match. Historical plans are not reported as currently scheduled. No run moves or completes actions, and every response fixes `outcome_forecast_allowed=false`.
- The real asset workflow calls the new APIs for calendar coverage, member calendars, date exceptions and schedule creation, and displays window capacity, utilization, item reasons and source/result SHA-256. The Node 24 TypeScript/Vite production build passes. Browser visual/click E2E was not rerun for this UI slice and remains pending.
- Real MySQL verifies two actions assigned to one member: an 8-hour Monday capacity produces two daily conflicts, an immutable replay preserves the original, an independent key preserves an equal-hash snapshot, and calendar version 2 at 16 hours creates a new feasible snapshot while the previous runs remain unchanged. Calendar event hashes chain correctly.
- The wider default regression passes `530 passed, 35 skipped`. On clean, GitHub/Gitee-synchronized commit `f7b4bfb`, the strict engineering gate passes Python 3.11.15, Node 24.14.0, 226 contracts, 6 crawler-lite, 91 acceptance, 20 Scheduler, 45 standalone Worker, 16 score, 48 evidence, 23 outbound-security, 26 Provider Gateway and 10 Xinghe adapter tests, 7/7 provider-native citation cases, 30/30 core Skill cases, Web production build, real MySQL `35 passed, 2 skipped`, offline SQL and real Alembic head `20260809_0038`.

### Still blocked

- Capacity is a governed manual planning input, not a contract, time sheet, invoice, actual spend or externally verified calendar. No Feishu, Yudao or other calendar connector has been supplied or validated.
- A feasible schedule only means the submitted estimates fit the submitted manual capacity and dependency snapshot. It is not a forecast of publication, citation, brand recommendation, revenue or retention.
- The strict report remains `BLOCKED`: authentication is `disabled/dev`, object storage is local rather than production HTTPS S3/MinIO, and optional Crawler/KB/content/workflow/Hermes services remain unconfigured `dev_only` capabilities.
- Consumer Browser L3 was deliberately not rerun. The last verified result remains 0/4: Doubao and Kimi require authenticated sessions, while Qianwen and DeepSeek require human verification. Provider API success cannot substitute for Consumer Web/App evidence.
- Production Yudao identity/directory, customer notification and publishing receipts, 20-case reviewer benchmark, Kimi credential rotation, DeepSeek model migration, real customer content quality/fairness and elapsed T+7/T+14/T+30 evidence remain open.

### Decision

- AIRank now turns evidence-backed opportunities into an auditable, resource-constrained 90-day delivery portfolio without inventing ROI. This slice is complete, but the product remains commercial `NO-GO` until external production, browser, publishing and customer-outcome gates pass.

## Governed brand graph gate (2026-08-09)

### Implemented and verified

- Alembic `20260809_0039` adds evidence-bound, optimistic-versioned brand/company/product/service entities, aliases, directional relations, previous-hash-linked events and immutable graph snapshots. The real MySQL database is at head with 101 AIRank tables.
- `airank.brand-graph.v1` only accepts a current approved FactRevision with no open conflict and active source evidence. Public JSON-LD additionally requires `public/redacted` disclosure; measurement-only records do not leak into public output.
- `airank.brand-graph-compiler.v1` normalizes identity tokens using NFKC/case/space/punctuation rules. Cross-entity ambiguity is excluded from measurement and JSON-LD, while a missing or ambiguous target brand blocks ScanRun creation. Historical project fields remain explicit `legacy_unverified` inputs and cannot emit public JSON-LD.
- ScanRun creation freezes graph snapshot/hash/status/limitations into the run and each task request. Worker parsing uses frozen target aliases and canonical competitor aliases, plus the task's frozen website/industry context. It never rereads mutable project or competitor names for a queued run.
- Real MySQL integration creates approved identity evidence, compiles a governed graph, freezes it into a blind scan, updates the entity to version 2 and confirms the original run still references version 1. The internal registry now contains 11 Skills and all 33 contract/holdout/adversarial cases pass.
- The knowledge and task-center UI uses real graph APIs and shows status, evidence bindings, ambiguity exclusions, limitations and hashes. Node 24 production build is required; this slice deliberately does not repeat Consumer Browser/visual E2E after the browser lifecycle was closed.
- On clean, GitHub/Gitee-synchronized commit `e1df49b`, the strict engineering gate passes Python 3.11.15, Node 24.14.0, 233 contracts, 6 crawler-lite, 96 acceptance, 20 Scheduler, 45 standalone Worker, 16 score, 48 evidence, 23 outbound-security, 26 Provider Gateway and 10 Xinghe adapter tests; Provider-native citations pass 7/7, core Skills pass 33/33, the Web production build passes, real MySQL passes `36 passed, 2 skipped`, and offline SQL plus real Alembic head `20260809_0039` pass. The explicit `required`/`yudao` authentication configuration check also passes. The overall result remains `BLOCKED`, because the run intentionally uses local object storage and has no real Yudao permission endpoint; optional Xinghe services remain unconfigured `dev_only` capabilities.

### Still blocked

- Existing projects have not been bulk-reviewed and migrated from `legacy_unverified`; an explicit human evidence review is required before their identity data can become governed or public.
- Predicate vocabulary governance, manual ambiguity adjudication, full Schema.org validator coverage and a real customer entity-resolution benchmark remain incomplete.
- Consumer Browser L3 remains at the last verified 0/4 and was not rerun. API evidence and a generated JSON-LD object cannot substitute for consumer-surface capture or prove that a model recommends the brand.
- Production Yudao authentication/directory, HTTPS object storage, customer publishing/notification receipts, 20-case reviewer benchmark, Kimi credential rotation, DeepSeek model migration and elapsed T+7/T+14/T+30 evidence remain open.

### Decision

- The measurement identity boundary is now versioned and evidence-governed, preventing alias drift and mutable competitor data from rewriting historical samples. This engineering slice is complete, but AIRank remains commercial `NO-GO` until all external production and customer-evidence gates pass.

## 2026-08-09 tenant Provider Credential Vault gate

- Feature commit `1acab04` adapts GEORank BYOK and TokHub keyring patterns into AIRank-owned `airank.provider-credential-vault.v1`; no upstream business code or UI was copied.
- Alembic `20260809_0040` adds tenant/provider/route credential envelopes and append-only events. AES-256-GCM uses random nonces and scope/version AAD; HMAC fingerprints use separate versioned material. Rotation and revocation scrub ciphertext and nonce, while request audits retain only credential source/id/version.
- Credential writes require trusted `airank:provider:admin`, optimistic version, reason, explicit billable confirmation and a successful L3 generation probe. Validation errors, API responses, logs, audit metadata and MySQL tests do not expose plaintext. Revoked tenant routes fail closed without environment fallback; an independent route may still fail over.
- Real MySQL verifies v1 activation → v1 rotated-out → v2 activation → v2 revoke as event sequences 1–4 with linked hashes. Both credential rows have empty ciphertext/nonce after final revoke, and all random test rows are cleaned. The database is at `20260809_0040` with 103 AIRank tables.
- On clean, GitHub/Gitee-synchronized feature commit `1acab04`, the strict gate passes 238 contract, 6 crawler-lite, 98 acceptance, 20 Scheduler, 45 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway and 10 Xinghe adapter tests; citation benchmark is 7/7, Skills are 33/33, Web build passes, real integration is `37 passed, 2 skipped`, and offline/real Alembic pass.
- Final status remains `BLOCKED`: production HTTPS S3/MinIO and real Yudao permission endpoints are absent; the vault still needs KMS/HSM, automated re-encryption and a real production four-provider tenant rotation; optional Xinghe integrations are `dev_only`; Consumer Browser L3 remains the last valid 0/4 and was not rerun or replaced with API/L2 evidence.

## 2026-08-09 Provider credential Operation Guard gate

- Feature commit `17060de` adds AIRank-owned persistent Operation Guard semantics to Provider credential upsert/revoke; `5e7da04` removes cross-tenant queue interference from a real integration fixture; `f94b07d` adds tenant/RBAC-scoped read-only operation reconciliation APIs and Settings UI. These commits are synchronized to GitHub/Gitee `main` and `codex/evidence-productization`.
- Alembic `20260809_0041` adds `airank_operation_guards` and `airank_operation_guard_events`, bringing the verified schema to 105 AIRank tables. The database stores only idempotency-key SHA-256, request hash, safe response, state and linked audit hashes; it does not store raw idempotency keys or credential plaintext.
- Successful same-request replay returns the original operation/credential result and does not repeat L3. Reusing a key with another payload, retrying a failed operation, or retrying after external effects began without a trustworthy terminal state fails closed. `OPERATION_OUTCOME_UNKNOWN` deliberately requires reconciliation and is not an exactly-once claim.
- Contract tests cover key rotation-stable replay, payload conflict, failed L3 suppression, concurrent unknown outcomes, mandatory headers, tenant isolation and permission enforcement. The read-only list/detail reports reconciliation count, replay status and event chain while omitting raw idempotency hashes and secret payloads. Real MySQL verifies upsert/replay/rotate/revoke, unknown state, three-event operation chains, linked credential events, secret/key absence and complete random-tenant cleanup.
- On clean, dual-remote-synchronized commit `f94b07d`, the strict executable gate passes 244 contract, 6 crawler-lite, 100 acceptance, 20 Scheduler, 45 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway and 10 Xinghe adapter tests; citation benchmark is 7/7, Skills are 33/33, Node 24 Web build passes, real integration is `37 passed, 2 skipped`, and offline/real Alembic pass at `0041`.
- Final status remains `BLOCKED / COMMERCIAL NO-GO`: the runtime still uses dev authentication and local object storage; production Yudao, KMS/HSM, automated re-encryption, four-provider production Vault rotation, remaining high-risk-write migration, customer publishing receipts and elapsed retest windows are open. Consumer Browser L3 remains the last valid 0/4 and was not rerun.

## 2026-08-09 internal Skill Trust Gate

- Feature commit `78b27b3`, release-gate commit `2766026` and runtime compatibility fix `80a36a7` adapt `yao-meta-skill` trust/package/install discipline into AIRank-owned manifests, schema, Trust Engine, API and UI. No upstream scripts or business UI were copied.
- All 11 manifests declare dependency references, network/secret/filesystem modes, `airank:skill:admin` and isolated-install roots. Static inspection follows each runner's local helper closure and fails closed on undeclared network, filesystem, secret, subprocess or dynamic-code capability; unsafe dependency specs, unresolved module/symbol/Skill refs, embedded secret literals and invalid entrypoints also block.
- `airank.skill-trust-report.v1` reports 11/11 `allow_local_execution`, zero blocked and isolated install passed. Promotion Ledger `1.1.0` binds registry/schema, implementation, eval/trust engines, external evidence list and trust report hash; trust failure becomes a promotion blocker and admin eval returns `409 SKILL_TRUST_BLOCKED` before runner execution.
- Real authenticated HTTP initially exposed a runtime-only failure: the isolated probe removed the repository-local virtualenv's legitimate `jsonschema` site-packages. `80a36a7` now runs Python with `-S`, removes repository source roots only, and adds the manifest-declared external dependency roots. CLI and the restarted long-running API both pass install simulation for 11 Skills.
- On clean, dual-remote-synchronized `80a36a7`, the strict gate independently reports Skill Trust PASS and also passes 246 contract, 6 crawler-lite, 101 acceptance, 20 Scheduler, 45 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway, 10 Xinghe adapter, 7/7 citation and 33/33 Skill eval tests; Node 24 Web build, real MySQL `37 passed, 2 skipped`, offline SQL and Alembic `0041` pass. The wider default suite passes `573 passed, 37 skipped`.
- API/Worker/Scheduler were restarted with process-memory-only four-provider credentials and valid keyrings. Health, trust report, credential portfolio and operation list return 200; all four routes remain `environment_legacy`, and recent logs contain zero ERROR/Traceback/CRITICAL markers. Consumer Browser was not rerun.
- Final status remains `BLOCKED / COMMERCIAL NO-GO`. The report deliberately fixes `claim_level=repository_gate_only` and `native_runtime_enforcement=false`; no OS sandbox, production Worker native permission guard or external installer probe has been demonstrated. Production Yudao/auth, HTTPS object storage, KMS/HSM, remaining external receipts and customer time-window evidence remain open.

## 2026-08-09 Provider Usage Ledger gate

- Feature commit `0c7bedc` adapts TokHub/TokKit usage precision and price-version concepts into AIRank-owned `airank.provider-usage-ledger.v1`; no upstream business code or UI was copied. The commit is synchronized to GitHub/Gitee `main` and `codex/evidence-productization`.
- Alembic `20260809_0042` adds non-null raw usage SHA-256, cost precision/source, tenant-scoped price versions and append-only cost derivations, bringing the verified schema to 107 AIRank tables. Provider billed amount plus currency is the only exact cost source; catalog multiplication is always estimated; missing Token or price remains unknown.
- Alembic `20260809_0043` binds each external publish attempt to one persistent `publisher.publish` Operation Guard. HTTP response loss now produces `outcome_unknown` and blocks every automatic replay; WordPress may only recover through a read-only deterministic-slug lookup. Real MySQL proves the success hash chain, zero duplicate POST after an unknown result, stale-attempt fail-closed behavior and GET-only WordPress reconciliation. This is not an exactly-once claim and customer-site receipts remain required.
- Successful and failed Provider calls use one persistence path. Price versions bind Provider, route, model, currency, per-million input/output rates, effective time, source reference/hash, reason and actor. Same-content replay is idempotent, stale or concurrent versions fail closed, secret-like evidence fields are rejected before database access, and historical price changes append derivations without overwriting raw usage.
- Admin contracts and Settings UI filter Provider, project, time, usage precision and cost precision. Summary fields deliberately say known cost and include coverage; mixed currency or any unpriced event keeps aggregate precision unknown. No demonstration price was inserted into the real tenant.
- On clean, dual-remote-synchronized `0c7bedc`, the strict gate passes 250 contract, 6 crawler-lite, 102 acceptance, 20 Scheduler, 45 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway, 10 Xinghe adapter, 7/7 citation and 33/33 Skill eval tests; Node 24 Web build, real integration `38 passed, 2 skipped`, offline SQL and real Alembic `0042` pass. The wider default suite passes `578 passed, 38 skipped`.
- API/Worker/Scheduler were restarted with process-memory-only four-provider credentials. Authenticated HTTP returns the new usage and price contracts: 18 real exact Token events, zero price versions, zero known-cost events, 0% coverage and aggregate cost precision unknown. Vault routes remain `environment_legacy`; current logs contain no new error markers. Consumer Browser was not rerun.
- Final status remains `BLOCKED / COMMERCIAL NO-GO`: runtime auth is dev/disabled and object storage is local; production Yudao, HTTPS object storage, KMS/HSM, official price synchronization, Provider invoice reconciliation, exchange-rate governance, finance receipts, customer publishing/notification receipts, reviewer benchmark and elapsed retest windows remain open. Consumer Browser L3 remains the last valid 0/4.

## 2026-08-09 Provider model lifecycle and migration gate

- Feature commit `2a13720` and release-check isolation fix `cf5f477` adapt TokHub model lifecycle governance into AIRank-owned `airank.provider-model-migration.v1`. Both commits are synchronized to GitHub/Gitee `main` and `codex/evidence-productization`; no upstream business code or UI was copied.
- Alembic `20260809_0044` adds tenant-scoped model migration plans and append-only events, bringing the verified schema to 109 AIRank tables. A plan binds Provider, route, current model, current configuration fingerprint and the manifest replacement. Concurrent identical `Idempotency-Key` requests create one plan; payload/key or basis conflicts fail closed.
- Target validation only accepts a request audit created after the plan with matching tenant, Provider, route, target model and configuration fingerprint, `outcome=success`, completion time and a non-empty Provider request ID. Approval is release-eligible only while the request audit and every event hash remain valid. Failure evidence is retained as `validation_failed`; later audit tampering immediately returns the release gate to blocked.
- Route API and Settings UI expose lifecycle state, sunset, days remaining, replacement, 30-day execution status, 90-day release status, migration version, L3 evidence status and event-chain integrity. A validated plan never overrides the execution stop window; switching the deployed model remains a separate deployment operation.
- On clean, dual-remote-synchronized `cf5f477`, the strict gate passes 255 contract, 6 crawler-lite, 107 acceptance, 20 Scheduler, 47 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway, 10 Xinghe adapter, 7/7 citation and 33/33 Skill eval tests; Node 24 Web build, real integration `39 passed, 2 skipped`, offline SQL and real Alembic `0044` pass. The wider default suite passes `589 passed, 39 skipped`.
- Runtime HTTP reports DeepSeek `deepseek-v3.2` with 62 days to the 2026-10-10 sunset: execution `pass`, release `blocked`, replacement `deepseek-v4-pro`, migration missing. The previous v4-pro request failed with an allocation/quota 403, so no successful audit, plan or approval was fabricated.
- Final status remains `BLOCKED / COMMERCIAL NO-GO`: v4-pro quota, real target L3 evidence, approved deployment migration, production Yudao auth, HTTPS object storage, KMS/HSM, customer publishing/notification receipts, reviewer benchmark, Consumer Web/App and elapsed retest evidence remain open. The Kimi credential exposed during acceptance must be rotated before production.

## 2026-08-09 Governed publication update and withdrawal

- Feature commit `c960d6a` and Browser release-probe authorization fix `5283357` are synchronized to GitHub/Gitee `main` and `codex/evidence-productization`. GEOFlow/TokHub patterns were reimplemented through AIRank-owned package, snapshot, Worker and Operation Guard contracts; no upstream business code or UI was copied.
- Alembic `20260809_0045` adds `publication_action`, `target_package_id`, `action_reason` and trusted `requested_by` lineage to existing publication packages while retaining 109 AIRank tables. Every update/withdraw creates a new `airank.publish-snapshot.v3`; historical content, review, receipt and retest evidence remain immutable.
- Only a `published` WordPress/HTTP package can be targeted. External publication evidence now requires `delivered` first, preventing a queued browser-created package plus typed URL from masquerading as a successful external publication. Replacement content must have a current matching approval. Active, delivered or outcome-unknown child actions block the next mutation; concurrent identical requests converge to one package under a target row lock and idempotent replay.
- WordPress update POSTs directly to the numeric remote ID in the original delivery receipt, with no slug lookup or new create. Withdrawal POSTs `status=draft`; no DELETE path exists. Generic HTTP uses `airank.publisher.v2` and includes action, target, reason and immutable content metadata. Response loss leaves the target unchanged, marks the action `outcome_unknown` and forbids replay/next mutation.
- Real MySQL runs the full local chain: initial HTTP delivery → publication evidence → concurrent idempotent update → original `superseded` → updated package evidence → withdrawal → both packages `withdrawn`. A second fixture verifies WordPress update hits `/posts/84` with one POST and no slug. Another real response-loss case proves the target remains `published`, the mutation becomes `outcome_unknown`, and a following withdrawal is rejected. Unit protocol fixtures also verify draft withdrawal and malicious remote ID zero egress.
- On clean, dual-remote-synchronized `5283357`, the strict gate passes 257 contract, 6 crawler-lite, 109 acceptance, 20 Scheduler, 50 Worker, 16 score, 48 evidence, 23 outbound-security, 32 Provider Gateway, 10 Xinghe adapter, 7/7 citation and 33/33 Skill eval tests; Node 24 Web build, real integration `39 passed, 2 skipped`, offline SQL and real Alembic `0045` pass. The wider default suite passes `596 passed, 39 skipped`; npm production audit reports 0 vulnerabilities.
- `--require-browser-providers` no longer implicitly launches persistent Browser profiles. Actual Consumer Browser L3 probes additionally require `AIRANK_RELEASE_RUN_BROWSER_PROBES=true`; without it, the gate explicitly blocks for missing current-run L3 evidence. This run intentionally kept it disabled under the existing no-rerun lifecycle constraint.
- Final status remains `BLOCKED / COMMERCIAL NO-GO`: production Yudao/auth, HTTPS S3/MinIO, KMS/HSM, customer WordPress/HTTP credentials and real initial/update/withdraw receipts, generic status-query/manual reconciliation, Consumer Web/App L3, reviewer benchmark, elapsed retest evidence and DeepSeek v4-pro migration remain open. The exposed Kimi credential still must be rotated before production.

## 2026-08-09 Governed publication outcome reconciliation

- Alembic `20260809_0046` adds tenant/project-scoped reconciliation cases, append-only hash-chain events and an attempt back-reference, bringing the verified local schema to 111 AIRank tables. It does not add a second publication truth store or an external retry job.
- Submission only accepts WordPress/HTTP packages whose latest attempt is `outcome_unknown` and whose matching `publisher.publish` Operation Guard is `external_started`. The request only supports observed success and requires an absolute URL, 2xx status, external receipt/remote ID, timezone-aware observation time, explanation and an immutable same-project object reference. The repository reads the stored bytes and verifies size and SHA-256 before accepting evidence.
- A distinct delivery admin must approve or reject. Self-review is rejected by authenticated actor identity. Rejection leaves package/attempt/Guard unknown and non-replayable. Approval atomically appends reconciliation and Guard events, completes the attempt/package and applies update/withdraw lineage; the transaction performs no external request.
- Manual receipts are explicitly labeled `receipt_origin=manual_reconciliation`, `reconciliation_method=two_person_manual_evidence` and `external_delivery_verified=false`. Non-withdraw packages return only to `delivered`; they still require separately recorded real publication evidence and a completed baseline before `published` or retest windows.
- Contract tests cover schema, evidence binding, self-review, hash continuity, rejection, replay and idempotency conflict. A real MySQL test verifies stored object bytes, a three-event case chain, a three-event Operation Guard chain, atomic package/attempt receipt persistence, retention of the original response-loss error and tenant cleanup. No customer publisher endpoint or Consumer Browser was called.
- This closes the missing local governance workflow, not the external truth blocker. Real customer initial/update/withdraw receipts, a real two-person customer reconciliation case, generic HTTP machine-readable status queries, production identity/object storage and all previously recorded release blockers remain required; commercial status stays `BLOCKED / NO-GO`.
