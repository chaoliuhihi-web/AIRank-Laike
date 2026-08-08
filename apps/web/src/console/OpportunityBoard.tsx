import type {
  InterventionOpportunity,
  OpportunityAction,
  OpportunityActionList,
  OpportunityActionRouting,
  OpportunityDependency,
  OpportunityExecutionPortfolio,
  OpportunityList,
  OpportunitySourceKind,
} from "./api";


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

const actionStateLabels: Record<OpportunityAction["status"], string> = {
  open: "待领取",
  in_progress: "执行中",
  evidence_blocked: "证据阻断",
  verified_not_observed: "复测未再观察到",
  waived: "已人工豁免",
};

const slaLabels: Record<OpportunityAction["sla_state"], string> = {
  on_track: "SLA 正常",
  due_soon: "24 小时内到期",
  overdue: "SLA 已逾期",
  final: "已终结",
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
  actionData,
  routingData,
  planningData,
  currentUserId,
  deriving,
  actingActionId,
  routingMutationKey,
  planningMutationKey,
  onDerive,
  onCreateAction,
  onClaimAction,
  onVerifyAction,
  onCreateTeam,
  onJoinTeam,
  onPutRoute,
  onSavePlan,
  onAddDependency,
  onWaiveDependency,
  onNavigate,
}: {
  data: OpportunityList;
  actionData: OpportunityActionList;
  routingData: OpportunityActionRouting;
  planningData: OpportunityExecutionPortfolio;
  currentUserId: string;
  deriving: boolean;
  actingActionId: string | null;
  routingMutationKey: string | null;
  planningMutationKey: string | null;
  onDerive: () => void;
  onCreateAction: (item: InterventionOpportunity) => void;
  onClaimAction: (item: OpportunityAction) => void;
  onVerifyAction: (item: OpportunityAction, verificationRunId: string) => void;
  onCreateTeam: (name: string) => void;
  onJoinTeam: (teamId: string) => void;
  onPutRoute: (sourceKind: OpportunitySourceKind, teamId: string) => void;
  onSavePlan: (action: OpportunityAction, effortHours: string, budgetAmount: string, assumptions: string, expectedVersion?: number) => void;
  onAddDependency: (action: OpportunityAction, prerequisiteActionId: string, rationale: string) => void;
  onWaiveDependency: (dependency: OpportunityDependency, waiverReason: string) => void;
  onNavigate: (path: string) => void;
}) {
  const latest = data.latest_derivation_run;
  const actionsByOpportunity = new Map(actionData.actions.map((item) => [item.opportunity_id, item]));
  const plansByAction = new Map(planningData.plans.map((item) => [item.action_id, item]));
  const currentOpportunityIds = new Set(data.opportunities.map((item) => item.opportunity_id));
  const currentUserTeamIds = new Set(
    routingData.teams
      .filter((team) => team.members.some((member) => member.user_id === currentUserId && member.status === "active"))
      .map((team) => team.team_id),
  );
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
                {actionsByOpportunity.get(item.opportunity_id) ? (
                  <>
                    <small>执行状态</small>
                    <strong>{actionStateLabels[actionsByOpportunity.get(item.opportunity_id)!.status]}</strong>
                    <span>{actionsByOpportunity.get(item.opportunity_id)!.assigned_to ? `责任人 ${actionsByOpportunity.get(item.opportunity_id)!.assigned_to}` : "尚未领取"}</span>
                  </>
                ) : null}
                <small>建议动作</small>
                <code>{item.recommended_action}</code>
                {actionsByOpportunity.get(item.opportunity_id) ? (
                  !actionsByOpportunity.get(item.opportunity_id)!.assigned_to && !["verified_not_observed", "waived"].includes(actionsByOpportunity.get(item.opportunity_id)!.status) ? (
                    <button type="button" disabled={actingActionId === actionsByOpportunity.get(item.opportunity_id)!.action_id} onClick={() => onClaimAction(actionsByOpportunity.get(item.opportunity_id)!)}>领取行动</button>
                  ) : (
                    <button type="button" onClick={() => onNavigate(routeFor(item))}>{actionLabel(item)}</button>
                  )
                ) : (
                  <button type="button" disabled={actingActionId === item.snapshot_id} onClick={() => onCreateAction(item)}>纳入执行</button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <section className="opportunity-routing-panel" aria-label="机会行动团队路由">
        <header>
          <div>
            <span className="opportunity-eyebrow">airank.opportunity-action-routing.v1</span>
            <h4>交付团队与容量路由</h4>
            <p>配置任一来源后即进入失败关闭模式：缺路由、非团队成员或容量耗尽都不能领取。手工成员不冒充 Yudao 已核验。</p>
          </div>
          <span data-mode={routingData.routing_mode}>
            {routingData.routing_mode === "team_routed" ? "四类路由就绪" : routingData.routing_mode === "blocked" ? "路由未完整" : "兼容无限制模式"}
          </span>
        </header>
        <form
          className="opportunity-routing-create"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const name = String(form.get("team_name") || "").trim();
            if (name) onCreateTeam(name);
          }}
        >
          <label>新团队<input name="team_name" defaultValue="GEO 交付组" minLength={1} maxLength={160} /></label>
          <button type="submit" disabled={routingMutationKey === "create-team"}>{routingMutationKey === "create-team" ? "创建中…" : "创建交付团队"}</button>
        </form>
        {routingData.teams.length === 0 ? (
          <p className="opportunity-routing-empty">尚未配置团队；当前保持显式 unrestricted_legacy，仅用于兼容，不代表生产路由完成。</p>
        ) : (
          <div className="opportunity-routing-teams">
            {routingData.teams.map((team) => (
              <article key={team.team_id}>
                <div><strong>{team.name}</strong><span>{team.member_count} 名成员 · {team.external_sync_state}</span></div>
                <div className="opportunity-routing-members">
                  {team.members.map((member) => (
                    <span key={member.member_id} data-capacity={member.at_capacity ? "full" : "available"}>
                      {member.display_name || member.user_id} · {member.active_action_count}/{member.max_active_actions}
                      {member.external_membership_verified ? " · Yudao 已核验" : " · 手工未核验"}
                    </span>
                  ))}
                </div>
                {!currentUserTeamIds.has(team.team_id) && (
                  <button type="button" disabled={routingMutationKey === `member:${team.team_id}`} onClick={() => onJoinTeam(team.team_id)}>
                    {routingMutationKey === `member:${team.team_id}` ? "加入中…" : "将当前账号加入团队"}
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
        {routingData.teams.length > 0 && (
          <div className="opportunity-routing-grid">
            {(Object.keys(sourceLabels) as OpportunitySourceKind[]).map((kind) => {
              const currentRoute = routingData.routes.find((route) => route.source_kind === kind);
              return (
                <article key={kind}>
                  <div><strong>{sourceLabels[kind]}</strong><span>{currentRoute ? `${currentRoute.team_name} · ${currentRoute.eligible_member_count} 可领取` : "未配置，已阻断"}</span></div>
                  <div>
                    {routingData.teams.map((team) => (
                      <button
                        type="button"
                        key={team.team_id}
                        data-active={currentRoute?.team_id === team.team_id}
                        disabled={routingMutationKey === `route:${kind}` || currentRoute?.team_id === team.team_id}
                        onClick={() => onPutRoute(kind, team.team_id)}
                      >
                        {currentRoute?.team_id === team.team_id ? "当前路由" : `路由到 ${team.name}`}
                      </button>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {actionData.actions.length > 0 && (
        <section className="opportunity-planning-panel" aria-label="机会执行预算与依赖">
          <header>
            <div>
              <span className="opportunity-eyebrow">airank.opportunity-execution-plan.v1</span>
              <h4>人工预算与前置依赖</h4>
              <p>工时和预算是实施人员估算，不是发票、实际支出或推荐增长预测。只有全部未终结行动拥有已批准计划时才汇总。</p>
            </div>
            <span data-complete={planningData.planning_coverage_complete}>
              {planningData.approved_plan_count}/{planningData.planning_required_count} 已批准
            </span>
          </header>
          <div className="opportunity-planning-summary">
            <div>
              <span>预算覆盖</span>
              <strong>{planningData.planning_coverage_complete ? "完整" : "不完整"}</strong>
            </div>
            <div>
              <span>人工估算工时</span>
              <strong>{planningData.total_estimated_effort_hours === null ? "—" : `${planningData.total_estimated_effort_hours} h`}</strong>
            </div>
            <div>
              <span>人工估算预算</span>
              <strong>{planningData.total_estimated_budget_amount === null ? "—" : `¥${planningData.total_estimated_budget_amount}`}</strong>
            </div>
            <div>
              <span>依赖阻断</span>
              <strong>{planningData.blocked_action_ids.length}</strong>
            </div>
          </div>
          {!planningData.planning_coverage_complete && (
            <p className="opportunity-planning-warning">
              汇总值保持空白：仍有 {planningData.unplanned_action_ids.length} 个未终结行动缺少已批准人工计划。
            </p>
          )}
          {planningData.topological_order.length > 0 && (
            <div className="opportunity-planning-order">
              <strong>可执行层级</strong>
              {planningData.topological_order.map((layer, index) => (
                <span key={`${index}-${layer.join("-")}`}>第 {index + 1} 层 · {layer.map(shortHash).join("、")}</span>
              ))}
            </div>
          )}
          <div className="opportunity-planning-list">
            {actionData.actions
              .filter((action) => !["verified_not_observed", "waived"].includes(action.status))
              .map((action) => {
                const plan = plansByAction.get(action.action_id);
                const availablePrerequisites = actionData.actions.filter((candidate) => candidate.action_id !== action.action_id);
                return (
                  <article key={action.action_id} data-blocked={planningData.blocked_action_ids.includes(action.action_id)}>
                    <div className="opportunity-planning-action-title">
                      <div>
                        <strong>{actionStateLabels[action.status]} · {shortHash(action.action_id)}</strong>
                        <span>{action.action_note}</span>
                      </div>
                      <span>{plan ? `${plan.status === "approved" ? "已批准" : "草稿"} · v${plan.version}` : "尚未计划"}</span>
                    </div>
                    <form
                      className="opportunity-plan-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const form = new FormData(event.currentTarget);
                        onSavePlan(
                          action,
                          String(form.get("effort_hours") || "").trim(),
                          String(form.get("budget_amount") || "").trim(),
                          String(form.get("assumptions") || "").trim(),
                          plan?.version,
                        );
                      }}
                    >
                      <label>人工工时<input name="effort_hours" type="number" min="0.01" max="10000" step="0.01" required defaultValue={plan?.estimated_effort_hours ?? "8"} /></label>
                      <label>预算（CNY）<input name="budget_amount" type="number" min="0" max="100000000" step="0.01" required defaultValue={plan?.estimated_budget_amount ?? "0"} /></label>
                      <label className="opportunity-plan-assumptions">估算依据<input name="assumptions" minLength={20} maxLength={4000} required defaultValue={plan?.assumptions ?? "由实施负责人根据当前证据范围人工估算，实际投入以交付记录为准。"} /></label>
                      <button type="submit" disabled={planningMutationKey === `plan:${action.action_id}`}>
                        {planningMutationKey === `plan:${action.action_id}` ? "保存中…" : "批准人工计划"}
                      </button>
                    </form>
                    {availablePrerequisites.length > 0 && (
                      <form
                        className="opportunity-dependency-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          const form = new FormData(event.currentTarget);
                          onAddDependency(
                            action,
                            String(form.get("prerequisite_action_id") || ""),
                            String(form.get("rationale") || "").trim(),
                          );
                        }}
                      >
                        <label>前置行动<select name="prerequisite_action_id" required defaultValue=""><option value="" disabled>选择前置行动</option>{availablePrerequisites.map((candidate) => <option value={candidate.action_id} key={candidate.action_id}>{shortHash(candidate.action_id)} · {actionStateLabels[candidate.status]}</option>)}</select></label>
                        <label>依赖依据<input name="rationale" minLength={12} maxLength={2000} required defaultValue="先完成前置行动并核验证据，再开始本行动。" /></label>
                        <button type="submit" disabled={planningMutationKey === `dependency:${action.action_id}`}>
                          {planningMutationKey === `dependency:${action.action_id}` ? "添加中…" : "添加前置依赖"}
                        </button>
                      </form>
                    )}
                    {plan?.dependencies.length ? (
                      <div className="opportunity-dependency-list">
                        {plan.dependencies.map((dependency) => (
                          <div key={dependency.dependency_id} data-satisfied={dependency.satisfied}>
                            <div>
                              <strong>{dependency.satisfied ? "依赖已满足" : "依赖阻断中"} · {shortHash(dependency.prerequisite_action_id)}</strong>
                              <span>{dependency.rationale}{dependency.waiver_reason ? ` · 豁免：${dependency.waiver_reason}` : ""}</span>
                            </div>
                            {dependency.status === "active" && !dependency.satisfied && (
                              <form
                                onSubmit={(event) => {
                                  event.preventDefault();
                                  const form = new FormData(event.currentTarget);
                                  onWaiveDependency(dependency, String(form.get("waiver_reason") || "").trim());
                                }}
                              >
                                <input name="waiver_reason" minLength={20} maxLength={2000} required defaultValue="经人工确认本轮可跳过前置行动，但不据此声明任何推荐或增长效果。" />
                                <button type="submit" disabled={planningMutationKey === `waive:${dependency.dependency_id}`}>
                                  {planningMutationKey === `waive:${dependency.dependency_id}` ? "记录中…" : "记录人工豁免"}
                                </button>
                              </form>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </article>
                );
              })}
          </div>
          <p className="opportunity-planning-disclaimer"><strong>效果声明：禁止。</strong> 当前没有自动日历排程，人工估算也不能替代合同、发票、工时单或发布后复测。</p>
        </section>
      )}

      {actionData.actions.length > 0 && (
        <section className="opportunity-action-queue" aria-label="机会行动台账">
          <header>
            <div>
              <span className="opportunity-eyebrow">airank.opportunity-action.v1</span>
              <h4>责任人与复测关闭</h4>
              <p>完成只允许表示最新完整复测中未再观察到，或记录人工豁免；两者都不等于品牌获得推荐或产生增长。</p>
            </div>
            <div className="opportunity-action-counts">
              <span>执行中 <strong>{actionData.open_count}</strong></span>
              <span>证据阻断 <strong>{actionData.evidence_blocked_count}</strong></span>
              <span>逾期 <strong>{actionData.overdue_count}</strong></span>
              <span>终结 <strong>{actionData.final_count}</strong></span>
            </div>
          </header>
          <div className="opportunity-action-list">
            {actionData.actions.map((action) => {
              const canVerify = Boolean(
                latest
                && !currentOpportunityIds.has(action.opportunity_id)
                && action.assigned_to === currentUserId
                && !["verified_not_observed", "waived"].includes(action.status),
              );
              return (
                <article key={action.action_id} data-sla={action.sla_state}>
                  <div>
                    <strong>{actionStateLabels[action.status]}</strong>
                    <span>{slaLabels[action.sla_state]} · 截止 {new Date(action.due_at).toLocaleString("zh-CN")}</span>
                  </div>
                  <p>{action.action_note}</p>
                  <div className="opportunity-action-proof">
                    <span>{action.assigned_to ? `责任人 ${action.assigned_to}` : "未领取"}</span>
                    <span>路由 {action.routing_state}{action.external_membership_verified ? " · Yudao 已核验" : " · 外部成员未核验"}</span>
                    <code title={action.latest_evidence_sha256}>{shortHash(action.latest_evidence_sha256)}</code>
                    <span>事件 {action.event_count} · 版本 {action.version}</span>
                    <span>SLA 升级 {action.escalation_count}{action.pending_escalation_count ? ` · ${action.pending_escalation_count} 待送达` : ""}{action.external_delivery_verified ? " · 外部已送达" : " · 外部未验证"}</span>
                    <strong>效果声明：禁止</strong>
                  </div>
                  {!action.assigned_to && !["verified_not_observed", "waived"].includes(action.status) && (
                    <button type="button" disabled={actingActionId === action.action_id} onClick={() => onClaimAction(action)}>由我领取</button>
                  )}
                  {canVerify && latest && (
                    <button type="button" disabled={actingActionId === action.action_id} onClick={() => onVerifyAction(action, latest.derivation_run_id)}>确认本轮未再观察到</button>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}
    </section>
  );
}
