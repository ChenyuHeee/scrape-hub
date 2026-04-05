"""Playwright browser lifecycle management with anti-detection."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright, BrowserContext, Page


# Anti-detection JavaScript injected into every page
_STEALTH_JS = """
// Remove navigator.webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
// Fake plugins
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
// Fake languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'zh-CN'],
});
// Remove automation traces
delete window.__playwright;
delete window.__pw_manual;
// Fake chrome runtime
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};
// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""

# Default Chromium launch flags for anti-detection
_DEFAULT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class BrowserManager:
    """
    Manages a Playwright persistent browser context with anti-detection.

    Usage::

        with BrowserManager(user_data_dir=".browser_data/x") as bm:
            page = bm.page
            page.goto("https://example.com")
    """

    def __init__(
        self,
        user_data_dir: str | Path = ".browser_data/default",
        headless: bool = False,
        locale: str = "en-US",
        viewport: dict | None = None,
        user_agent: str | None = None,
        extra_args: list[str] | None = None,
    ):
        self.user_data_dir = Path(user_data_dir)
        self.headless = headless
        self.locale = locale
        self.viewport = viewport or {"width": 1280, "height": 900}
        self.user_agent = user_agent or _USER_AGENT
        self.extra_args = extra_args or []

        self._pw = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Use as context manager.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not started. Use as context manager.")
        return self._context

    def __enter__(self) -> BrowserManager:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        """Launch the persistent browser context."""
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
            viewport=self.viewport,
            locale=self.locale,
            user_agent=self.user_agent,
            args=_DEFAULT_ARGS + self.extra_args,
            ignore_default_args=["--enable-automation"],
        )
        self._page = (
            self._context.pages[0] if self._context.pages else self._context.new_page()
        )
        self._page.add_init_script(_STEALTH_JS)

    def close(self) -> None:
        """Close browser and playwright."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def new_page(self) -> Page:
        """Create a new page in the same context."""
        page = self.context.new_page()
        page.add_init_script(_STEALTH_JS)
        return page
