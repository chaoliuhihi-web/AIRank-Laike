# scripts

开发和运维辅助脚本。

## 计划脚本

```text
agent_control.py       三 AI 协作控制：生成下一轮 prompt、MacPro 总控 brief、基础 gate report
release_readiness.py   真实上线门禁：测试、构建、迁移、远端和 capability probe 必须通过
seed-fixtures.sh       灌入测试企业、竞品和问题数据
scan-manual.sh         手动触发 AI 平台采样
dev-setup.sh           本地开发环境初始化
db-migrate.sh          数据库迁移
export-report.sh       手动导出报告
provider-profile-login.sh  打开指定消费端 AI 网页 profile，供运维完成登录/真人验证
```

## 使用说明

所有脚本从仓库根目录运行，不要 cd 到 scripts 目录内执行。

## 三 AI 自动协作

CodexMacPro 生成总控 brief 和三台 AI 下一轮 prompt：

```bash
python3 scripts/agent_control.py director --write
```

单独生成某台 AI 下一轮 prompt：

```bash
python3 scripts/agent_control.py next codex-win --write
python3 scripts/agent_control.py next codex-imac --write
python3 scripts/agent_control.py next codex-macpro --write
```

运行基础 gate：

```bash
python3 scripts/agent_control.py gate --write
```

## 上线门禁

真实 beta 上线前运行：

```bash
python3 scripts/release_readiness.py --database-url "$AIRANK_RELEASE_DATABASE_URL"
```

该命令会执行 contracts、acceptance、scheduler、worker、score、evidence、provider gateway、Provider 引用基准、核心 Skill 评测、独立 Skill Trust Gate、xinghe-adapter、Web build、真实 integration tests、Alembic 离线 SQL、真实 MySQL migration 和 capability probe。普通自动测试会隔离 `AIRANK_DATABASE_URL` 等数据库环境变量，真实 migration 与 integration tests 只使用 `--database-url` 或 `AIRANK_RELEASE_DATABASE_URL`。只要必需能力仍是 `dev_only` / `blocked` / `partial`，Skill trust/安装模拟失败，或真实 MySQL migration/integration 失败，脚本会返回非零，不能声明 release ready。

生产发布还必须加上消费端网页 Provider 门禁：

```bash
AIRANK_PROVIDER_MODE=browser \
AIRANK_BROWSER_PROFILE_DIR=.runtime/browser-profiles \
python3 scripts/release_readiness.py \
  --database-url "$AIRANK_RELEASE_DATABASE_URL" \
  --require-optional-capabilities \
  --require-browser-providers
```

`--require-browser-providers` 会把 Consumer Browser L3 设为发布必需项，但默认不会自行打开浏览器。只有同时显式设置 `AIRANK_RELEASE_RUN_BROWSER_PROBES=true` 才会打开各 Provider 的持久浏览器 profile 并执行可能较慢、可能触发登录/真人验证的真实生成探测。未设置该开关时门禁固定 `BLOCKED`，明确说明本轮没有产生 Browser L3 证据，而不是用导入错误或旧结果代替。

首次部署或 cookie 过期时，用非 headless 方式初始化对应 profile：

```bash
AIRANK_BROWSER_PROFILE_DIR=/var/lib/airank/browser-profiles \
  scripts/provider-profile-login.sh chatgpt
```

如果消费端平台对 Playwright 自带测试浏览器触发真人验证，可改用部署机已安装的
Chrome，同时继续使用 AIRank 的独立持久 profile：

```bash
AIRANK_BROWSER_CHANNEL=chrome \
AIRANK_BROWSER_PROFILE_DIR=/var/lib/airank/browser-profiles \
  scripts/provider-profile-login.sh chatgpt
```

也可以用 `all` 顺序初始化全部 provider。完成后必须重跑带 `--require-browser-providers` 的上线门禁。

## 本地真实控制台数据

本地 Web + API 联调前先灌入演示项目，避免控制台资产和报表页面退回前端 fixture：

```bash
AIRANK_DATABASE_URL="mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4" \
  scripts/seed-fixtures.sh
```

默认写入 `tenant_demo` / `project_demo`，可用 `AIRANK_SEED_TENANT_ID` 和 `AIRANK_SEED_PROJECT_ID` 覆盖。
