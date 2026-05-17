# packages/score

AIRank 来客指数计算。

v0 指标：

```text
品牌提及率 20
推荐率 20
引用率 15
竞品压制程度 15
事实一致性 15
高购买意图覆盖 10
答案稳定性 5
```

输出要能解释每一分从哪里来，并能关联扫描快照、引用来源和事实卡。

## M2 pure function baseline

`packages/score/src/airank_score` exposes `calculate_airank_score(snapshot)`.
The function is deterministic and has no I/O, clock, random or database access.

Current M2 inputs:

- answer snapshot id
- brand mention flag
- brand rank
- source citation ids

Future inputs that are not available yet, such as FactAtom consistency and
competitor suppression, score `0` with `pending_input` rather than inventing a
conclusion. Every non-pending component carries snapshot/citation evidence refs.
