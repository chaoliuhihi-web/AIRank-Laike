from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_login_page_is_chinese_and_airank_branded() -> None:
    source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text()
    login_source = source.split("function LoginPage", 1)[1].split(
        "function ActionToast", 1
    )[0]

    for expected in (
        "AIRank 来客",
        "企业 GEO 增长平台",
        "欢迎登录",
        "企业租户编号",
        "账号",
        "密码",
        "登录 AIRank",
        "/favicon.svg",
    ):
        assert expected in login_source

    for leaked_copy in (
        "Sign in",
        "Signing in",
        "Product console",
        "Use yudao credentials",
        "Yudao tenant",
        "AIRANK_AUTH_MODE=dev_only",
    ):
        assert leaked_copy not in login_source
