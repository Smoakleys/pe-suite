"""Playwright source scaffold — browser-driven scraping with interactive login.

This is the pattern the heavy Material Tracking / Updates sources will follow. It uses
Playwright's *sync* API with a **persistent context** rooted at the app's browser
profile dir, so a one-time interactive login (the user signs in the first time the
browser opens) persists across fetches and restarts — no credentials stored by us.
(Later: swap to env-var credentials behind `requires_auth`, no shape change.)

Optional by design: Playwright + a browser binary are heavy, so this is not registered
by default and degrades gracefully if Playwright isn't installed. Enable with:

    pip install playwright && python -m playwright install chromium

`PlaywrightSource` is the reusable base; `ExamplePlaywrightSource` is a runnable demo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import RawSnapshot, Record
from ..source import BaseSource, FetchContext


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


class PlaywrightSource(BaseSource):
    """Base for browser-driven sources. Subclasses implement `scrape(page) -> bytes`
    and `parse`. The persistent context keeps the user logged in between runs."""

    url: str = ""
    headless: bool = False  # show the browser so the user can log in the first time

    def fetch(self, ctx: FetchContext) -> RawSnapshot:
        from playwright.sync_api import sync_playwright

        profile = ctx.browser_profile_dir
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile) if profile else "",
                headless=self.headless,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.url, wait_until="domcontentloaded")
                content = self.scrape(page)
            finally:
                context.close()
        return RawSnapshot(content=content, content_type="text/html",
                           meta={"url": self.url})

    def scrape(self, page) -> bytes:
        """Default: capture the full rendered HTML. Override for richer extraction."""
        return page.content().encode("utf-8")


class ExamplePlaywrightSource(PlaywrightSource):
    id = "playwright_example"
    name = "Example.com (Playwright demo)"
    group = "updates"
    requires_auth = False
    headless = True
    refresh_after = timedelta(minutes=30)
    url = "https://example.com/"

    def parse(self, raw: RawSnapshot) -> list[Record]:
        import re
        html = raw.content.decode("utf-8", errors="replace")
        m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = m.group(1).strip() if m else "(no title)"
        return [Record(
            source_id=self.id, group=self.group, kind="page", key=self.url,
            title=title, body="Rendered via Playwright (Chromium).", url=self.url,
            project_id=None, timestamp=datetime.now(timezone.utc),
            data={"bytes": len(raw.content)},
        )]
