"""Optional Playwright smoke test.

This is intentionally excluded from the offline pytest default. It requires:
    pip install playwright
    playwright install chromium
    python -m uvicorn app.main:create_app --factory
    python scripts/e2e_browser.py

The in-process HTTP E2E is covered by tests/test_api_flows.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_URL = os.environ.get("EGWA_BASE_URL", "http://127.0.0.1:8000")
ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright가 설치되지 않았습니다: pip install playwright", file=sys.stderr)
        return 2

    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            print(f"브라우저 실행 실패: {exc}\nplaywright install chromium", file=sys.stderr)
            return 2

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("button", name="① 충분 근거").click()
        page.get_by_text("승인 대기").first.wait_for(timeout=15000)

        page.get_by_role("button", name="승인 전 실행 시도 (409 확인)").click()
        page.get_by_text("E_STATE_CONFLICT").first.wait_for(timeout=10000)
        page.screenshot(path=str(ARTIFACTS / "01-before-approval-409.png"), full_page=True)
        page.locator("section.card").filter(
            has=page.get_by_role("heading", name="사람 승인")
        ).first.screenshot(path=str(ARTIFACTS / "01-approval-409.png"))

        page.get_by_role("button", name="승인", exact=True).click()
        page.get_by_text("승인됨").first.wait_for(timeout=10000)

        page.get_by_role("button", name="모의 실행", exact=True).click()
        page.get_by_text("모의 실행 완료").first.wait_for(timeout=15000)
        page.screenshot(path=str(ARTIFACTS / "02-executed.png"), full_page=True)

        page.get_by_role("button", name="같은 키로 재요청 (멱등 확인)").click()
        page.get_by_text("같은 idempotency key 재요청").first.wait_for(timeout=10000)
        page.screenshot(path=str(ARTIFACTS / "03-idempotent-replay.png"), full_page=True)
        page.locator("section.card").filter(
            has=page.get_by_role("heading", name="모의 실행")
        ).first.screenshot(path=str(ARTIFACTS / "03-execution.png"))

        browser.close()
    print("browser e2e passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
