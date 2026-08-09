from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_customer_navigation_is_a_six_step_growth_loop() -> None:
    routes = read("apps/web/src/console/routes/console-routes.ts")

    assert 'audience: "customer"' in routes
    assert 'label: "买家问题"' in routes
    assert 'label: "多平台扫描"' in routes
    assert 'label: "证据缺口"' in routes
    assert 'label: "可信事实"' in routes
    assert 'label: "答案资产"' in routes
    assert 'label: "发布与复测"' in routes
    for step in range(1, 7):
        assert f"step: {step}" in routes

    customer_navigation = routes.split("export const customerRoutes", 1)[1].split(
        "export const deliveryRoutes", 1
    )[0]
    assert 'label: "任务中心"' not in customer_navigation
    assert 'label: "证据中心"' not in customer_navigation
    assert 'label: "Skill 控制台"' not in customer_navigation
    assert 'label: "Provider 健康"' not in customer_navigation


def test_delivery_and_admin_workspaces_are_separate_routes() -> None:
    routes = read("apps/web/src/console/routes/console-routes.ts")
    app = read("apps/web/src/App.tsx")

    assert 'path: "/delivery"' in routes
    assert 'path: "/delivery/tasks"' in routes
    assert 'path: "/delivery/evidence"' in routes
    assert 'path: "/delivery/reviews"' in routes
    assert 'path: "/admin"' in routes
    assert 'path: "/admin/providers"' in routes
    assert 'path: "/admin/skills"' in routes
    assert 'path: "/admin/operations"' in routes
    assert 'path === "/admin/providers"' in app
    assert 'path === "/admin/skills"' in app
    assert 'path === "/delivery/tasks"' in app


def test_legacy_customer_routes_redirect_to_business_context() -> None:
    routes = read("apps/web/src/console/routes/console-routes.ts")

    assert '"/console/checkup": "/console/scans"' in routes
    assert '"/console/tasks": "/console/scans"' in routes
    assert '"/console/evidence": "/console/scans"' in routes
    assert '"/console/page-audit": "/console/assets/site-audit"' in routes
    assert '"/console/skills": "/admin/skills"' in routes


def test_production_console_does_not_export_business_fallbacks() -> None:
    api = read("apps/web/src/console/api.ts")
    app = read("apps/web/src/App.tsx")

    assert "fallbackConsoleOverview" not in api
    assert "fallbackAssetBundle" not in api
    assert "fallbackReportList" not in api
    assert '"error" | "ready"' in app
    assert "生产环境不使用固定业务数据" in app


def test_auth_session_carries_permissions_for_pre_render_filtering() -> None:
    api = read("apps/web/src/console/api.ts")
    backend = read("apps/api/main.py")

    assert "permissions: string[];" in api
    assert "permissions: list[str]" in backend
    assert "routeIsAccessible" in read("apps/web/src/console/routes/console-routes.ts")


def test_dashboard_uses_backend_growth_loop_conclusion_gate() -> None:
    api = read("apps/web/src/console/api.ts")
    app = read("apps/web/src/App.tsx")
    backend = read("apps/api/main.py")

    assert 'contract_version: "airank.growth-loop.v1"' in api
    assert "fetchGrowthLoop(overview.project.id" in app
    assert 'growthLoop?.conclusion_readiness.state === "ready"' in app
    assert 'f"{API_PREFIX}/projects/{{project_id}}/growth-loop"' in backend
    assert "PROVIDER_EVIDENCE_UNAVAILABLE" in backend


def test_workspace_header_does_not_mutate_navigation_order() -> None:
    sidebar = read("apps/web/src/console/layout/ConsoleSidebar.tsx")

    assert "[...routesForAudience(audienceForPath(activePath))]" in sidebar
    assert "sidebarRef.current?.scrollTo({ top: 0 })" in sidebar
