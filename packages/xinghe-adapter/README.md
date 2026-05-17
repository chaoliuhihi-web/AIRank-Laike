# packages/xinghe-adapter

AIRank 对接 `XingheAI2026V2` 的唯一边界。

## 职责

- 探测星河侧能力状态。
- 将 AIRank contracts 转换为星河侧 API / job / event payload。
- 统一 trace、run、error、blocked reason。
- 提供 fallback 信息，保证 AIRank 不因星河能力不可用而整体不可用。

## 子模块

```text
auth/       yudao 用户、租户、权限
model/      yudao 模型与 API Key 权威源
crawler/    Crawler Gateway
kb/         KB / Qdrant / Brand Corpus
workflow/   workflow-runner
content/    智能出版 / 内容工厂
hermes/     Hermes 自动化
status/     capability readiness
```

## 红线

- 不 import `XingheAI2026V2` 内部模块。
- 不读取主仓 `.runtime` 当作产品真相源。
- 不吞掉星河侧错误。
- 不把 `partial` 能力包装成 `ready`。

## M4 capability probe

`airank_xinghe_adapter.CapabilityProbe` outputs a capability matrix with:

- `ready`: authenticated or reachable probe succeeded.
- `partial`: optional Xinghe/Hermes endpoint is configured but not healthy.
- `blocked`: required MVP dependency is missing or failed.
- `dev_only`: local/mock fallback is usable for development but not release-ready.

Covered capabilities:

- `yudao_auth`
- `yudao_tenant_user`
- `object_storage`
- `xinghe_crawler_gateway`
- `xinghe_kb_service`
- `xinghe_creator_marketing`
- `xinghe_workflow_runner`
- `xinghe_hermes`

The probe reads deployment environment variables and does not import
`XingheAI2026V2` internals. Local object storage and missing optional Xinghe
endpoints are reported as `dev_only` with explicit fallbacks.
