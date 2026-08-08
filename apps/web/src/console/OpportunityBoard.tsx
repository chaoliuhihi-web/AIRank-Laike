import type { InterventionOpportunity, OpportunityList, OpportunitySourceKind } from "./api";


const sourceLabels: Record<OpportunitySourceKind, string> = {
  brand_visibility: "品牌可见度",
  citation_support: "引用支持",
  fact_governance: "事实治理",
  page_extractability: "页面可提取性",
};

const stateLabels: Record<InterventionOpportunity["state"], string> = {
  blocked_evidence: "证据待补",
  ready_for_action: "可执行",
  monitor: "观察中",
};

const evidenceLabels: Record<InterventionOpportunity["evidence_level"], string> = {
  quality_gated_repeated_samples: "质量门禁重复样本",
  independently_reviewed_source_page: "来源页独立人工终审",
  immutable_governance_record: "不可变治理记录",
  content_hashed_page_audit: "正文哈希页面审计",
  immutable_claim_citation_basis: "不可变 Claim / Citation 基础",
};

function routeFor(item: InterventionOpportunity): string {
  if (item.source_kind === "citation_support") return "/console/evidence";
  if (item.source_kind === "fact_governance" || item.intervention_gate === "evidence_blocked") return "/console/facts";
  if (item.source_kind === "page_extractability") return "/console/page-audit";
  return "/console/assets";
}

function actionLabel(item: InterventionOpportunity): string {
  if (item.intervention_gate === "content_action_ready") return "继续下方内容干预";
  if (item.source_kind === "citation_support") return "去证据中心复核";
  if (item.source_kind === "page_extractability") return "去页面审计修复";
  return "去企业事实库处理";
}

function shortHash(value: string): string {
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}

export function OpportunityBoard({
  data,
  deriving,
  onDerive,
  onNavigate,
}: {
  data: OpportunityList;
  deriving: boolean;
  onDerive: () => void;
  onNavigate: (path: string) => void;
}) {
  const latest = data.latest_derivation_run;
  return (
    <section className="opportunity-board" data-testid="cross-domain-opportunity-board">
      <header className="opportunity-board-header">
        <div>
          <span className="opportunity-eyebrow">airank.intervention-opportunity.v1</span>
          <h3>跨域干预机会</h3>
          <p>统一品牌未提及、引用支持、事实治理和页面技术问题。优先分只用于行动排序，不是品牌推荐率或增长预测。</p>
        </div>
        <button className="airank-console-primary-button" type="button" disabled={deriving} onClick={onDerive}>
          {deriving ? "正在冻结证据…" : latest ? "重新生成不可变快照" : "生成机会快照"}
        </button>
      </header>

      {latest ? (
        <>
          <div className="opportunity-summary" aria-label="机会快照摘要">
            <div><span>本轮机会</span><strong>{latest.opportunity_count}</strong></div>
            <div><span>可执行</span><strong>{data.state_counts.ready_for_action}</strong></div>
            <div><span>证据待补</span><strong>{data.state_counts.blocked_evidence}</strong></div>
            <div><span>新增 / 持续</span><strong>{latest.new_count} / {latest.persisting_count}</strong></div>
            <div><span>本轮未再观察到</span><strong>{latest.cleared_count}</strong></div>
          </div>
          <div className="opportunity-proof-line">
            <span>评估时间 {new Date(latest.evaluated_at).toLocaleString("zh-CN")}</span>
            <span>证据基础 <code title={latest.source_basis_sha256}>{shortHash(latest.source_basis_sha256)}</code></span>
            <span>知识有效期窗口 {latest.knowledge_window_days} 天</span>
          </div>
          {latest.cleared_count > 0 && (
            <p className="opportunity-cleared-note">
              {latest.cleared_count} 项只表示在当前完整派生中未再观察到；必须下钻新证据确认，不自动标成“已解决”。
            </p>
          )}
          <div className="opportunity-source-strip" aria-label="机会来源分布">
            {(Object.keys(sourceLabels) as OpportunitySourceKind[]).map((kind) => (
              <span key={kind}>{sourceLabels[kind]} <strong>{data.source_counts[kind]}</strong></span>
            ))}
          </div>
        </>
      ) : (
        <div className="opportunity-empty">
          <strong>尚未生成跨域机会快照</strong>
          <span>系统不会从营销模板补造机会；至少需要一条受治理的缺口、引用、事实或页面审计证据。</span>
        </div>
      )}

      {data.opportunities.length > 0 && (
        <div className="opportunity-list">
          {data.opportunities.map((item) => (
            <article className="opportunity-card" data-kind={item.source_kind} data-state={item.state} key={item.snapshot_id}>
              <div className="opportunity-card-score" aria-label={`行动优先分 ${item.priority_score}`}>
                <strong>{item.priority_score}</strong>
                <span>行动优先分</span>
                <small>非推荐率</small>
              </div>
              <div className="opportunity-card-content">
                <div className="opportunity-card-tags">
                  <span>{sourceLabels[item.source_kind]}</span>
                  <span data-state={item.state}>{stateLabels[item.state]}</span>
                  <span>{item.severity}</span>
                </div>
                <h4>{item.title}</h4>
                <p>{item.description}</p>
                <dl className="opportunity-factor-grid">
                  <div><dt>严重度</dt><dd>{item.score_factors.severity_points}</dd></div>
                  <div><dt>证据强度</dt><dd>{item.score_factors.evidence_points}</dd></div>
                  <div><dt>紧迫度</dt><dd>{item.score_factors.urgency_points}</dd></div>
                </dl>
                <div className="opportunity-card-proof">
                  <span>{evidenceLabels[item.evidence_level]}</span>
                  <code title={item.source_evidence_sha256}>{shortHash(item.source_evidence_sha256)}</code>
                  <code>{item.issue_code}</code>
                </div>
              </div>
              <div className="opportunity-card-action">
                <small>建议动作</small>
                <code>{item.recommended_action}</code>
                <button type="button" onClick={() => onNavigate(routeFor(item))}>{actionLabel(item)}</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
