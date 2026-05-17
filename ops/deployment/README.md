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

## Schema review

- M1 schema/index review is documented in `docs/architecture/mysql-schema-plan.md`.
- Production schema truth is Alembic under `apps/api/alembic`; this bootstrap SQL remains a local initialization snapshot.
- Deployment users and grants stay in `ops/deployment/mysql-bootstrap.sql`, while Alembic migrations create only AIRank application schema objects.
