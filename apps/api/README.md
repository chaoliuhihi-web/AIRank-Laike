# apps/api

AIRank 产品 API。

第一版技术栈：

- FastAPI
- SQLAlchemy
- Alembic
- MySQL

API 统一使用 `/api/v1` 前缀。响应、错误码、分页、幂等和 trace 规则见 `packages/contracts/api-conventions.md` 与 `packages/contracts/error-codes.md`。

核心模块：

- projects
- competitors
- questions
- scans
- facts
- gaps
- assets
- publishing
- reports
- leads
- integrations

API 只依赖 AIRank contracts/domain。跨仓能力必须通过 `packages/xinghe-adapter`。API 不直接访问 yudao 数据库，也不保存 yudao model resolve 返回的 API Key 明文。
