# AIRank CI 与质量门禁

## 目标

M1 之前先建立轻量 CI，防止文档、契约和 SQL 继续漂移。代码落地后再逐步增加 lint、test 和 coverage。

## M0 门禁

- 架构入口文件存在。
- MySQL bootstrap 存在。
- 禁止回退旧术语：`FactCard`、`fact_card`、`ready_for_pattern`。
- bootstrap SQL 至少包含核心表和 `airank_async_jobs` 心跳字段。
- contracts 目录必须包含 API 约定和错误码文档。

## M1 门禁

- Python lint。
- API unit tests。
- Alembic migration 检查。
- contract schema 校验。
- worker job 状态机测试。

## M2 门禁

- outbox dispatcher 测试。
- 多租户隔离测试。
- 报告证据链验收测试。
- adapter capability status 测试。

## GitHub Actions

基础 workflow 已放在 `.github/workflows/ci.yml`。当前仓库尚未进入编码阶段，所以先执行 shell 静态检查；后续 `apps/api` 初始化后，在同一 workflow 中补 Python 环境、依赖安装、lint 和 test。
