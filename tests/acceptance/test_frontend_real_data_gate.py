from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_console_static_data_file_contains_no_business_results() -> None:
    source = (ROOT / "apps" / "web" / "src" / "console" / "data.ts").read_text(encoding="utf-8")

    assert source.strip() == 'export type Tone = "primary" | "success" | "warning" | "danger" | "muted";'


def test_console_pages_use_real_api_or_explicit_capability_state() -> None:
    app_source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    api_source = (ROOT / "apps" / "web" / "src" / "console" / "api.ts").read_text(encoding="utf-8")

    for api_call in (
        "fetchProviderReadiness",
        "fetchCitationSupport",
        "fetchPageAudits",
        "createPageAudit",
        "fetchKnowledgeSources",
        "saveKnowledgeSource",
        "searchKnowledge",
        "fetchKnowledgeGovernance",
        "fetchFactConflicts",
        "fetchFacts",
        "fetchBuyerQuestions",
        "fetchQuestionObservationBatches",
        "importQuestionObservations",
        "fetchMeasurementQuality",
        "fetchPublishPackages",
        "fetchPublicationReconciliations",
        "fetchPublishAttempts",
        "createPublishPackage",
        "createPublishMutation",
        "recordPublicationEvidence",
        "submitPublicationReconciliation",
        "reviewPublicationReconciliation",
        "fetchKnowledgeSyncPolicies",
        "fetchKnowledgeSyncRuns",
        "createKnowledgeSyncPolicy",
        "triggerKnowledgeSync",
        "updateKnowledgeSyncPolicy",
        "fetchRetestWindows",
        "fetchReports",
    ):
        assert api_call in app_source
        assert f"function {api_call}" in api_source or f"async function {api_call}" in api_source

    for fake_result in (
        "56.8%",
        "38.7%",
        "本月 AI 来客线索",
        "示例科技有限公司",
        "较上周 ↑ 8%",
        "竞品A",
        "已抓取页面\" value=\"96",
        "留资率\" value=\"18.7%",
        "project_demo",
    ):
        assert fake_result not in app_source

    assert "当前明确标记为 disabled" in app_source
    assert "不能据此证明因果" not in app_source  # cautious conclusion comes from the real report API
    assert "次数不是搜索量" in app_source
    assert "客户提供观察记录（未独立核验）" in app_source
    assert "来源内出现次数必须是" in app_source
    assert 'metricNumber("not_mentioned_count")' in app_source
    assert 'showLauncher ? "收起重新扫描" : "重新扫描"' in app_source
    assert "质量阻断" in app_source
    assert 'item.status === "quality_blocked"' in app_source
    assert "技术可提取性分不等于品牌推荐率" in app_source
    assert "引用选择 ≠ 引用支持" in app_source
    assert "不可变来源页面 + 不同审核人一致/裁决" in app_source
    assert "创建不可变发布包" in app_source
    assert "登记真实发布证据" in app_source
    assert "更新 / 撤回已发布内容" in app_source
    assert "未知发布结果 · 双人证据对账" in app_source
    assert "非原生回执" in app_source
    assert "不执行 DELETE" in app_source
    assert "客户站点凭证只允许由 Worker 安全注入" in app_source
    assert "published_url" in api_source
    assert "baseline_run_id" in api_source
    assert "公开来源自动同步" in app_source
    assert "内容变化只会追加新修订" in app_source
    assert "系统不会擅自发现或抓取未授权站点" in app_source
    route_source = (ROOT / "apps" / "web" / "src" / "console" / "routes" / "console-routes.ts").read_text(encoding="utf-8")
    assert 'path: "/console/assets/site-audit"' in route_source
    assert '"/console/page-audit": "/console/assets/site-audit"' in route_source
    assert 'label: "官网可提取性"' in route_source


def test_backend_exposes_console_list_contracts() -> None:
    api_source = (ROOT / "apps" / "api" / "main.py").read_text(encoding="utf-8")
    delivery_source = (ROOT / "apps" / "api" / "delivery_routes.py").read_text(encoding="utf-8")
    reconciliation_source = (ROOT / "apps" / "api" / "publication_reconciliation.py").read_text(encoding="utf-8")
    retest_source = (ROOT / "apps" / "api" / "retest_routes.py").read_text(encoding="utf-8")

    assert 'f"{API_PREFIX}/projects/{{project_id}}/buyer-questions"' in api_source
    assert '"/projects/{project_id}/publish-packages"' in delivery_source
    assert '"/publish-packages/{package_id}/mutations"' in delivery_source
    assert '"/publish-packages/{package_id}/reconciliations"' in reconciliation_source
    assert '"/publish-reconciliations/{case_id}/review"' in reconciliation_source
    assert '"/projects/{project_id}/retest-windows"' in retest_source
