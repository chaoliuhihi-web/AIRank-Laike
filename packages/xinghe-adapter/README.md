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
