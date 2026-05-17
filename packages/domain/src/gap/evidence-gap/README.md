# gap/evidence-gap — 内容/信源缺口

识别企业距离"被 AI 推荐"还缺哪些内容、事实和信源。

客户侧常用页面名：**内容缺口工厂**，在推荐门槛页面里也可叫**推荐证据缺口**。
内部模型名：`EvidenceGap`

## 缺口类型

```text
案例页不足
FAQ 不足
参数表不足
行业方案不足
第三方信源不足
价格说明不足
资质证明不足
竞品对比不足
技术抓取不足
```

## 每个缺口显示

```text
缺口名称
影响问题数
竞品是否覆盖
影响评分
优先级
建议动作
预计改善方向
生成状态
发布状态
复测状态
```

## 与 suppression 的关系

- `suppression` 回答"竞品为什么排在前面"。
- `evidence-gap` 回答"我缺什么推荐证据"。
- 两者共同构成 `gap` 父模块，对应 PRD 第 11.5 节。

## M3 traceability rule

`airank_domain.ContentGap` is valid only when it can be traced to all of:

- at least one buyer question id
- at least one source citation id
- at least one FactAtom id

`packages/evidence.generate_gap_from_citations(...)` bridges source citations and
sourced FactAtom objects into a traceable content gap. This prevents generating
gap recommendations from unsupported claims.
