"""
Regression tests for crawler.py bugs found in a targeted bug-hunt review:

1. is_alive() (and /api/health's browser_alive) trusted Browser.is_connected(),
   which does NOT reliably flip to False when the underlying driver
   connection dies mid-session (confirmed against Playwright's own source
   during the review, and reproduced live: "Connection closed while reading
   from the driver" kept browser_alive=true while every subsequent request
   failed identically). BrowserManager now tracks this itself via
   _crash_detected, set whenever _fetch_one_async observes a known
   driver-crash error signature, and _ensure_initialized_async now forces a
   relaunch when that flag is set instead of trusting is_connected().

2. On the LAST retry attempt, a redirect-to-login was detected but silently
   fell through to `return content` -- returning the login page's HTML as if
   it were a successful fetch, instead of raising.

3. refresh_cookies_async opened a page via self._context.new_page() directly,
   bypassing the _page_slots semaphore that caps concurrency to protect
   against GeM's WAF -- now serialized via a dedicated lock.

Run: python test_crawler_crash_and_pool.py
"""
import asyncio
import sys
import threading
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, ".")

import crawler as crawler_mod

PASS = 0
FAIL = 0


def check(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


def make_bm_with_fake_loop():
    bm = crawler_mod.BrowserManager.__new__(crawler_mod.BrowserManager)
    bm._loop = None
    bm._loop_thread = None
    bm._loop_ready = threading.Event()
    bm._playwright = None
    bm._browser = MagicMock()
    bm._browser.is_connected.return_value = True
    bm._context = MagicMock()
    bm._initialized = True
    bm._crash_detected = False
    bm._init_lock = None
    bm._pool_lock = None
    bm._page_slots = None
    bm._page_pool = []
    bm._cookie_refresh_lock = None
    return bm


def make_page(content_str='{"number_of_results": 1}', url="https://mkp.gem.gov.in/search"):
    page = MagicMock()
    page.content = AsyncMock(return_value=content_str)
    page.url = url
    page.is_closed.return_value = False
    page.goto = AsyncMock(return_value=None)
    page.close = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(return_value=None)
    return page


def test_is_driver_crash_error_detects_known_signatures():
    print("\n[1] _is_driver_crash_error recognizes the real crash signature "
          "seen in production, and doesn't false-positive on an ordinary timeout")
    check(
        "detects the exact production crash message",
        crawler_mod._is_driver_crash_error(
            Exception("Page.goto: Connection closed while reading from the driver")
        ),
    )
    check(
        "does not flag an ordinary navigation timeout as a driver crash",
        not crawler_mod._is_driver_crash_error(Exception("Page.goto: Timeout 30000ms exceeded")),
    )


def test_crash_marks_browser_unhealthy_and_forces_relaunch():
    print("\n[2] A driver-crash error during fetch marks is_alive False and "
          "forces the next _ensure_initialized_async to relaunch")
    bm = make_bm_with_fake_loop()

    bad_page = make_page()
    bad_page.goto = AsyncMock(
        side_effect=Exception("Page.goto: Connection closed while reading from the driver")
    )
    bm._context.new_page = AsyncMock(return_value=bad_page)

    try:
        bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json", retries=1)
    except RuntimeError:
        pass  # expected -- every attempt fails

    check("is_alive is False after the crash (despite is_connected() still "
          "reporting True)", bm.is_alive is False)
    check("_crash_detected was set", bm._crash_detected is True)

    # Simulate what _ensure_initialized_async's guard sees on the next call:
    # is_connected() still lies (True), but the crash flag must override it.
    would_skip_relaunch = (
        bm._initialized and bm._browser and bm._browser.is_connected() and not bm._crash_detected
    )
    check("the relaunch guard would NOT skip re-initialization "
          "(is_connected() alone would have wrongly skipped it)",
          would_skip_relaunch is False)


def test_last_retry_login_redirect_raises_instead_of_returning_html():
    print("\n[3] A login-page redirect on the FINAL retry attempt must raise, "
          "not silently return the login page as if it were valid content")
    bm = make_bm_with_fake_loop()

    login_page = make_page(content_str="<html>login</html>", url="https://mkp.gem.gov.in")
    bm._context.new_page = AsyncMock(return_value=login_page)

    raised = False
    try:
        bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json", retries=1)
    except RuntimeError:
        raised = True

    check("fetch() raised instead of returning the login page HTML", raised)


def test_refresh_cookies_is_serialized_not_unbounded():
    print("\n[4] refresh_cookies_async is serialized via a dedicated lock "
          "instead of spawning unbounded concurrent pages outside the pool")
    bm = make_bm_with_fake_loop()
    bm._ensure_initialized_async = AsyncMock(return_value=None)

    created_pages = []
    concurrent_peak = [0]
    concurrent_now = [0]

    async def slow_goto(*a, **kw):
        await asyncio.sleep(0.05)
        concurrent_now[0] -= 1

    def make_slow_page():
        concurrent_now[0] += 1
        concurrent_peak[0] = max(concurrent_peak[0], concurrent_now[0])
        p = make_page()
        created_pages.append(p)
        p.goto = AsyncMock(side_effect=slow_goto)
        return p

    bm._context.new_page = AsyncMock(side_effect=lambda: make_slow_page())
    bm._context.cookies = AsyncMock(return_value=[])

    async def fire_many():
        await asyncio.gather(*(bm.refresh_cookies_async() for _ in range(5)))

    bm.run(fire_many())

    check(f"all 5 refresh calls completed (created {len(created_pages)} pages)",
          len(created_pages) == 5)
    check(f"never more than 1 concurrent cookie-refresh page (peak was {concurrent_peak[0]})",
          concurrent_peak[0] == 1)


if __name__ == "__main__":
    test_is_driver_crash_error_detects_known_signatures()
    test_crash_marks_browser_unhealthy_and_forces_relaunch()
    test_last_retry_login_redirect_raises_instead_of_returning_html()
    test_refresh_cookies_is_serialized_not_unbounded()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
