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

该命令会执行 contracts、acceptance、worker、score、evidence、xinghe-adapter、Web build、真实 integration tests、Alembic 离线 SQL、真实 MySQL migration 和 capability probe。普通自动测试会隔离 `AIRANK_DATABASE_URL` 等数据库环境变量，真实 migration 与 integration tests 只使用 `--database-url` 或 `AIRANK_RELEASE_DATABASE_URL`。只要必需能力仍是 `dev_only` / `blocked` / `partial`，或真实 MySQL migration/integration 失败，脚本会返回非零，不能声明 release ready。

生产发布还必须加上消费端网页 Provider 门禁：

```bash
AIRANK_PROVIDER_MODE=browser \
AIRANK_BROWSER_PROFILE_DIR=.runtime/browser-profiles \
python3 scripts/release_readiness.py \
  --database-url "$AIRANK_RELEASE_DATABASE_URL" \
  --require-optional-capabilities \
  --require-browser-providers
```

`--require-browser-providers` 会打开 ChatGPT、DeepSeek、Kimi、通义、豆包、百度 AI 搜索和腾讯元宝的持久浏览器 profile。任何平台未登录、需要真人验证或找不到可输入问题的控件，都会让 release gate 返回非零。

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
