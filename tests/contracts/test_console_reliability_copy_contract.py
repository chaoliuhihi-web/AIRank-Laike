from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_console_localizes_api_errors_and_does_not_render_false_zero_summaries() -> None:
    api_source = (ROOT / "apps" / "web" / "src" / "console" / "api.ts").read_text()
    app_source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text()

    assert 'AUTH_PERMISSION_FORBIDDEN: "当前账号缺少此功能权限。"' in api_source
    assert 'RETEST_COMPARE_RUN_REQUIRED: "需要至少一个已完成且口径可比的测量批次。"' in api_source
    assert "localizeApiError(payload.error?.message, payload.error?.code, fallback)" in api_source

    skill_source = app_source.split("function SkillConsolePage", 1)[1].split(
        "function SettingsSection", 1
    )[0]
    assert '!loadError && skills.length > 0' in skill_source
    assert "加载完成前不展示默认数量或晋级结论" in skill_source

    settings_source = app_source.split("function SettingsPage", 1)[1].split(
        "function SkillConsolePage", 1
    )[0]
    assert "无权限或不可用" in settings_source
    assert "providerRoutesLoaded" in settings_source
    assert "providerPricesLoaded" in settings_source
    assert "!providerPriceError && providerPricesLoaded" in settings_source
    assert "加载完成前不展示录入表单、版本数量或空数据结论" in settings_source


def test_provider_health_page_uses_persisted_l3_copy() -> None:
    app_source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text()
    checkup_source = app_source.split("function CheckupPage", 1)[1].split(
        "function pageAuditTone", 1
    )[0]

    assert "最近一次已存证 L3 探测" in checkup_source
    assert "不会在页面加载时重复发起计费探测" in checkup_source
    assert 'item.status === "ready" ? "已就绪" : "已阻断"' in checkup_source
