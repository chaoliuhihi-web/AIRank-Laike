# packages/evidence

证据链、回答快照、source index 和下载回执。

AIRank 的报告必须可复盘：

- 每个 AI 回答保存原文、平台、模型、问题、时间和 run_id。
- 每个引用来源保存 URL、来源类型、所属方、抓取状态和快照。
- 每个报告保存 source index 和 evidence bundle。
- 下载导出需要有 receipt，方便交付验收。

该包复用 `XingheAI2026V2` creator-marketing 的 report evidence 思路，但不复制其内部实现。

## M2 mock/manual provider

`packages/evidence/src/airank_evidence` defines the first testable evidence
objects:

- `AnswerSnapshot` stores the AI answer, question, provider, run, task and brand
  visibility fields.
- `SourceCitation` stores URL, host, title, cited text and source type.
- `MockAnswerProvider` builds deterministic snapshots from worker job payloads.

The provider refuses to create an answer snapshot without at least one citation.
This keeps scan and report code from producing unsupported conclusions.

## M3 FactAtom source bridge

`fact_source_ref_from_citation(citation)` converts an answer source citation into
a domain `FactSourceRef`. Confirmed FactAtom objects must carry one of these
traceable source refs, so no confirmed fact can exist without citation/object/URL
provenance.
