# AIRank 数据迁移策略

## 结论

M0 可以保留 `ops/deployment/mysql-bootstrap.sql` 作为本地初始化快照，但生产 schema 真相源必须从 M1 开始切到 Alembic migration。

## 目录建议

```text
apps/api/
  alembic.ini
  migrations/
    env.py
    versions/
      0001_initial_airank_schema.py
```

## 规则

- `0001_initial_airank_schema.py` 必须与当前 `ops/deployment/mysql-bootstrap.sql` 对齐。
- 生产环境只执行 Alembic migration，不直接执行手写 bootstrap SQL。
- 每次 schema 变更必须有 migration、回滚说明和数据回填说明。
- 禁止在业务代码启动时自动 `CREATE TABLE`。
- 禁止跳过 migration 直接改生产库。

## Review 清单

每个 migration PR 必须回答：

- 是否影响 `tenant_id` 过滤。
- 是否新增或修改索引。
- 是否影响 worker 正在执行的 job。
- 是否需要 backfill。
- 是否兼容旧版本 API / worker。
- 是否涉及敏感字段或密钥。
- 是否需要更新 `mysql-schema-plan.md` 和 contracts。

## Bootstrap SQL 的定位

`ops/deployment/mysql-bootstrap.sql` 仅用于：

- 本地快速初始化。
- 架构评审。
- 与 Alembic 初始迁移对照。

M1 之后，如果两者不一致，以 Alembic migration 为准，并更新 bootstrap 快照。

## M0 到 M1 执行顺序

1. 确认当前 bootstrap SQL 无 P0 字段缺失。
2. 初始化 `apps/api`。
3. 初始化 Alembic。
4. 生成 `0001_initial_airank_schema.py`。
5. 在空库执行 `alembic upgrade head`。
6. 对比表数量、字段、索引与 bootstrap SQL。
7. CI 增加 migration 静态检查。
