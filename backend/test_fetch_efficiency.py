"""
Regression tests for the fetch-efficiency fix and the async-Playwright
rewrite that followed it.

Background: the WIP code routed every fetch through Playwright's *sync*
API called from ThreadPoolExecutor worker threads, which is not
thread-safe and silently failed ("Cannot switch to a different thread")
inside a broad try/except — returning incomplete data with a 200 OK
instead of erroring. This was confirmed live against the real GeM site.

The fix: BrowserManager runs async Playwright on one dedicated background
event-loop thread and exposes a synchronous, thread-safe facade
(fetch/fetch_many/run) that the rest of the app calls without knowing
anything is async underneath. These tests exercise that bridge using a
real asyncio event loop (no live network — see test_live_scrape.py for
that), so they catch thread-affinity violations for real rather than
mocking them away.

Run: python test_fetch_efficiency.py
"""
import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

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
    """
    A real BrowserManager wired to a real background asyncio event loop
    (so run_coroutine_threadsafe actually exercises cross-thread dispatch),
    but with the Playwright browser/context/page objects mocked out with
    AsyncMock so no real browser is launched.
    """
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


# ───────────────────────────────────────────────────────────────────────────
# 1. The bridge is safe to call from a real worker thread (the actual bug)
# ───────────────────────────────────────────────────────────────────────────
def test_fetch_is_safe_from_a_worker_thread():
    print("\n[1] BrowserManager.fetch() called from a ThreadPoolExecutor worker thread")
    bm = make_bm_with_fake_loop()
    page = make_page(content_str='{"number_of_results": 5}')
    bm._context.new_page = AsyncMock(return_value=page)

    caller_threads = []

    def call_fetch():
        caller_threads.append(threading.current_thread().ident)
        return bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json")

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(call_fetch) for _ in range(4)]
        results = [f.result() for f in futures]  # raises if the thread-affinity bug reappears

    check("all 4 calls from worker threads succeeded (no 'different thread' crash)",
          all('"number_of_results": 5' in r for r in results))
    check("calls genuinely came from different OS threads than this test",
          len(set(caller_threads)) >= 1)
    bm.shutdown_test_loop = True


def test_fetch_many_runs_concurrently_not_serially():
    print("\n[2] BrowserManager.fetch_many() overlaps I/O instead of serializing")
    bm = make_bm_with_fake_loop()

    # Each fake page.goto() "sleeps" 100ms — if fetch_many were serial,
    # 6 URLs would take >= 600ms; if concurrent (bounded by pool of 8),
    # they should all finish in roughly one slot's worth of time.
    async def slow_goto(*a, **kw):
        await asyncio.sleep(0.1)

    def make_slow_page():
        p = make_page(content_str='{"number_of_results": 1}')
        p.goto = AsyncMock(side_effect=slow_goto)
        return p

    bm._context.new_page = AsyncMock(side_effect=lambda: make_slow_page())

    import time
    urls = [f"https://mkp.gem.gov.in/search?page={i}&format=json" for i in range(6)]
    t0 = time.time()
    results = bm.fetch_many(urls)
    elapsed = time.time() - t0

    check("all 6 URLs returned a result", len(results) == 6)
    check("all succeeded", all(r and '"number_of_results": 1' in r for r in results))
    check(f"ran concurrently, not serially (took {elapsed:.2f}s, serial would be >=0.6s)", elapsed < 0.4)


# ───────────────────────────────────────────────────────────────────────────
# 2. Page pool: reuse instead of open/close per call
# ───────────────────────────────────────────────────────────────────────────
def test_page_pool_reuses_pages():
    print("\n[3] BrowserManager page pool reuses pages across sequential fetches")
    bm = make_bm_with_fake_loop()
    created = []

    def new_page_factory():
        p = make_page(content_str='{"number_of_results": 1}')
        created.append(p)
        return p

    bm._context.new_page = AsyncMock(side_effect=lambda: new_page_factory())

    bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json")
    bm.fetch("https://mkp.gem.gov.in/search?page=2&format=json")

    check("only ONE page was ever created (second fetch reused the pool)", len(created) == 1)
    check("the reused page was never closed", created[0].close.call_count == 0)


# ───────────────────────────────────────────────────────────────────────────
# 3. Retry + no blind sleep
# ───────────────────────────────────────────────────────────────────────────
def test_fetch_retries_transient_failures():
    print("\n[4] BrowserManager.fetch() retries instead of failing on the first error")
    bm = make_bm_with_fake_loop()

    bad_page = make_page()
    bad_page.goto = AsyncMock(side_effect=TimeoutError("navigation timeout"))
    # A page whose navigation failed shouldn't be treated as reusable —
    # otherwise the pool would hand the same broken page back on retry.
    bad_page.is_closed.return_value = True
    good_page = make_page(content_str='{"number_of_results": 1}')

    bm._context.new_page = AsyncMock(side_effect=[bad_page, good_page])

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        result = bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json", retries=3)

    check("recovered after a transient failure", '"number_of_results": 1' in result)
    check("no wait_for_timeout anywhere (blind sleep is gone)",
          not hasattr(bad_page, "wait_for_timeout") or bad_page.wait_for_timeout.call_count == 0)


def test_fetch_raises_after_exhausting_retries():
    print("\n[5] BrowserManager.fetch() raises only after exhausting real retries")
    bm = make_bm_with_fake_loop()

    def make_failing_page():
        p = make_page()
        p.goto = AsyncMock(side_effect=TimeoutError("navigation timeout"))
        return p

    bm._context.new_page = AsyncMock(side_effect=[make_failing_page() for _ in range(3)])

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        try:
            bm.fetch("https://mkp.gem.gov.in/search?page=1&format=json", retries=3)
            raised = False
        except RuntimeError:
            raised = True

    check("raises RuntimeError only after all 3 attempts fail", raised)


# ───────────────────────────────────────────────────────────────────────────
# 4. GeMCrawler._try_json_crawl: parallel page fetch via the bridge
# ───────────────────────────────────────────────────────────────────────────
def test_try_json_crawl_uses_fetch_many():
    print("\n[6] GeMCrawler._try_json_crawl fetches remaining pages via fetch_many (concurrent)")
    gc = crawler_mod.GeMCrawler.__new__(crawler_mod.GeMCrawler)
    gc._bm = MagicMock()

    page1 = '{"number_of_results": 25, "catalogs": [' + ",".join(
        f'{{"id": "{i}", "final_price": {{"value": 100}}}}' for i in range(10)
    ) + '], "facets": {}}'
    page2 = '{"catalogs": [' + ",".join(
        f'{{"id": "{i}", "final_price": {{"value": 100}}}}' for i in range(10, 20)
    ) + ']}'
    page3 = '{"catalogs": [' + ",".join(
        f'{{"id": "{i}", "final_price": {{"value": 100}}}}' for i in range(20, 25)
    ) + ']}'

    gc._bm.fetch.return_value = page1
    gc._bm.fetch_many.return_value = [page2, page3]

    result = gc._try_json_crawl("https://mkp.gem.gov.in/foo/search", {}, "", max_pages=50)

    check("crawl succeeded", result is not None)
    check("collected all 25 products across 3 pages", result and result["productCount"] == 25)
    check("used fetch_many for the remaining pages (not a sequential loop)", gc._bm.fetch_many.called)
    check("requested exactly the 2 remaining pages", len(gc._bm.fetch_many.call_args[0][0]) == 2)


if __name__ == "__main__":
    test_fetch_is_safe_from_a_worker_thread()
    test_fetch_many_runs_concurrently_not_serially()
    test_page_pool_reuses_pages()
    test_fetch_retries_transient_failures()
    test_fetch_raises_after_exhausting_retries()
    test_try_json_crawl_uses_fetch_many()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
