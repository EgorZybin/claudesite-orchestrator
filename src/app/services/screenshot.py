from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ScreenshotError(Exception):
    """Browser launch / navigation / capture failure."""


def take_screenshot(
    url: str,
    *,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    timeout_seconds: float = 30.0,
    full_page: bool = False,
) -> bytes:
    """Запустить chromium headless, перейти на URL, вернуть PNG-bytes.

    Args:
        url: ссылка с http(s)://.
        viewport_width / height: размер окна (desktop 1280×800 by default).
        timeout_seconds: лимит на goto + networkidle.
        full_page: если True — скриншот всей страницы (длинный),
            иначе только viewport (быстрее и обычно достаточно для hero).

    Returns:
        PNG bytes.

    Raises:
        ScreenshotError: любая ошибка в Playwright (launch/timeout/crash).
    """
    try:
        from playwright.sync_api import (
            Error as PWError,
            TimeoutError as PWTimeoutError,
            sync_playwright,
        )
    except ImportError as e:
        raise ScreenshotError(f"playwright not installed: {e}") from e

    timeout_ms = int(timeout_seconds * 1000)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height},
                    user_agent=(
                        "Mozilla/5.0 (claudesite-analyze/0.1) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120 Safari/537.36"
                    ),
                )
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except PWTimeoutError as e:
                    raise ScreenshotError(f"goto timeout for {url}: {e}") from e
                except PWError as e:
                    raise ScreenshotError(f"navigation failed for {url}: {e}") from e

                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
                except PWTimeoutError:
                    logger.info("screenshot_networkidle_timeout url=%s — proceeding", url)

                try:
                    png = page.screenshot(full_page=full_page, type="png")
                except PWError as e:
                    raise ScreenshotError(f"capture failed for {url}: {e}") from e

                logger.info(
                    "screenshot_ok url=%s size=%d viewport=%dx%d full_page=%s",
                    url, len(png), viewport_width, viewport_height, full_page,
                )
                return png
            finally:
                browser.close()
    except ScreenshotError:
        raise
    except Exception as e:
        raise ScreenshotError(f"playwright failed: {type(e).__name__}: {e}") from e
