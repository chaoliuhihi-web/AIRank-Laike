# ops/deployment

部署配置和环境说明。

生产部署和交付给第三方的步骤见：

- `ops/deployment/production-deployment.md`
- `ops/deployment/compose.production.yml`
- `ops/deployment/env.production.example`
- `ops/deployment/Dockerfile.backend`
- `ops/deployment/Dockerfile.web`
- `ops/deployment/compose.single-node.production.yml`
- `ops/deployment/single-node-production.md`

生产配置在任何服务启动前由 `scripts/production_preflight.py` 失败关闭；
`/api/v1/health` 是存活探针，`/api/v1/ready` 才是部署就绪探针。

第一版目标：

- AIRank 可独立部署。
- XingheAI2026V2 adapter 全部可配置、可关闭。
- 任一星河能力不可用时，AIRank 返回 partial/blocked，不影响核心 MVP 运行。

## 本地 MySQL

建库脚本：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
```

该脚本可重复执行，会修复本地 dev `airank` 用户的密码和常见本机/Docker
Desktop/Docker bridge 来源 host 授权，包括 `127.0.0.1`、`localhost`、
`192.168.65.%` 和 `172.20.%`。若仍出现 `Access denied for user 'airank'@'...'`，
用 root 检查是否存在更具体的同名 host 记录：

```sql
SELECT user, host FROM mysql.user WHERE user = 'airank';
```

本地环境变量：

```bash
set -a
source ops/deployment/env.example
set +a
```

详细说明见 `docs/architecture/mysql-schema-plan.md`。

真实本地集成验证：

```bash
AIRANK_RUN_REAL_MYSQL=1 \
AIRANK_DATABASE_URL="$AIRANK_DATABASE_URL" \
python3 -m pytest tests/integration -q
```

真实 yudao 集成验证需要本地 yudao 已启动，并在 shell 中提供本地测试账号：

```bash
AIRANK_RUN_REAL_YUDAO=1 \
YUDAO_BASE_URL=http://127.0.0.1:48080 \
YUDAO_TENANT_ID=1 \
YUDAO_USERNAME="$YUDAO_USERNAME" \
YUDAO_PASSWORD="$YUDAO_PASSWORD" \
python3 -m pytest tests/integration -q
```

## Schema review

- M1 schema/index review is documented in `docs/architecture/mysql-schema-plan.md`.
- Production schema truth is Alembic under `apps/api/alembic`; this bootstrap SQL remains a local initialization snapshot.
- Deployment users and grants stay in `ops/deployment/mysql-bootstrap.sql`, while Alembic migrations create only AIRank application schema objects.
