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
python3 scripts/release_readiness.py
```

该命令会执行 contracts、acceptance、worker、score、evidence、xinghe-adapter、Web build、Alembic 离线 SQL、真实 MySQL migration 和 capability probe。只要必需能力仍是 `dev_only` / `blocked` / `partial`，或真实 MySQL migration 失败，脚本会返回非零，不能声明 release ready。
