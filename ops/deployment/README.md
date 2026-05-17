# ops/deployment

部署配置和环境说明。

第一版目标：

- AIRank 可独立部署。
- XingheAI2026V2 adapter 全部可配置、可关闭。
- 任一星河能力不可用时，AIRank 返回 partial/blocked，不影响核心 MVP 运行。

## 本地 MySQL

建库脚本：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
```

本地环境变量：

```bash
set -a
source ops/deployment/env.example
set +a
```

详细说明见 `docs/architecture/mysql-schema-plan.md`。
