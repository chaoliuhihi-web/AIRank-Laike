#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROVIDER="${1:-}"
if [[ -z "$PROVIDER" ]]; then
  echo "usage: scripts/provider-profile-login.sh <chatgpt|deepseek|kimi|tongyi|doubao|baidu_ai_search|yuanbao|all>" >&2
  exit 2
fi

PROVIDERS=(chatgpt deepseek kimi tongyi doubao baidu_ai_search yuanbao)
if [[ "$PROVIDER" == "all" ]]; then
  TARGETS=("${PROVIDERS[@]}")
else
  TARGETS=("$PROVIDER")
fi

export AIRANK_PROVIDER_MODE="${AIRANK_PROVIDER_MODE:-browser}"
export AIRANK_BROWSER_HEADLESS=0
export AIRANK_BROWSER_TIMEOUT_SECONDS="${AIRANK_BROWSER_TIMEOUT_SECONDS:-300}"
export AIRANK_BROWSER_PROFILE_DIR="${AIRANK_BROWSER_PROFILE_DIR:-$ROOT/.runtime/browser-profiles}"
export AIRANK_BROWSER_CAPTURE_DIR="${AIRANK_BROWSER_CAPTURE_DIR:-$ROOT/.runtime/browser-captures}"

for target in "${TARGETS[@]}"; do
  echo "[provider-login] opening $target with profile root: $AIRANK_BROWSER_PROFILE_DIR"
  PROVIDER="$target" python3 - <<'PY'
import os
from apps.api.provider_scan import browser_provider_config, probe_provider_readiness
from playwright.sync_api import sync_playwright

provider = os.environ["PROVIDER"]
config = browser_provider_config(provider)
with sync_playwright() as playwright:
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(config.profile_dir),
        headless=False,
        viewport={"width": 1440, "height": 1000},
        locale="zh-CN",
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(config.url, wait_until="domcontentloaded", timeout=int(config.timeout_seconds * 1000))
    print(f"[provider-login] {provider}: complete login/human verification in the opened browser.")
    input("[provider-login] press Enter here after the prompt box is visible...")
    context.close()

result = probe_provider_readiness(provider)
print(f"[provider-login] {provider}: {result.status} {result.blocker_code or ''} {result.reason or ''}".strip())
if result.status != "ready":
    raise SystemExit(1)
PY
done

echo "[provider-login] done"
