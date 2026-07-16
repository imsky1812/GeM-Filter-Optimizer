"""
Regression tests for three bugs in scraper.py found in a targeted bug-hunt
review:

1. _find_category_url used self._session.get(...) directly for its two real
   GeM network calls -- the one place in the file that bypassed the
   Playwright-backed _fetch() bridge, which exists specifically because
   plain requests calls are blocked by GeM's WAF (per _fetch's own
   docstring).

2. The cookie-refresh throttle stored its timestamp on the *instance*
   (self._last_cookie_refresh_time) while guarding it with a *class*-level
   lock -- but main.py creates a fresh GeMScraper() per request, so the
   throttle never actually engaged: every request launched a full extra
   headless Chromium via sync_playwright() in __init__.

3. _names_match's `len(k1) > 5` guard made two short but identical
   (post-normalization) spec names -- e.g. a real golden facet "BIS" vs a
   differently-punctuated "B.I.S" rendering on a product page -- never
   match, silently dropping that filter's data.

Run: python test_scraper_waf_and_names.py
"""
import sys
import time

sys.path.insert(0, ".")

from scraper import GeMScraper

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


class NoNetworkSession:
    """A fake requests.Session that raises if any network method is used --
    proves _find_category_url never falls back to the raw, WAF-blocked path."""

    class _Cookies:
        def __init__(self):
            self.set_calls = []

        def clear(self):
            pass

        def set(self, *a, **k):
            self.set_calls.append((a, k))

    def __init__(self):
        self.cookies = self._Cookies()

    def get(self, *args, **kwargs):
        raise AssertionError(
            "raw self._session.get() was called -- this bypasses the "
            "WAF-safe _fetch() bridge"
        )

    def close(self):
        pass


class FakeFetchScraper(GeMScraper):
    """Real GeMScraper with the network boundary (_fetch) stubbed and a
    session that fails loudly if anything tries to use it directly."""

    def __init__(self, fetch_responses):
        self._session = NoNetworkSession()
        self._fetch_responses = fetch_responses
        self._fetch_calls = []

    def _fetch(self, url, retries=3):
        self._fetch_calls.append(url)
        for matcher, response in self._fetch_responses:
            if matcher in url:
                return response
        raise AssertionError(f"unexpected _fetch call: {url}")


SEARCH_RESULTS_HTML = """
<html><body>
<a href="/interactive-panels-with-cpu/search">Interactive Panels</a>
</body></html>
"""

CATEGORY_JSON = '{"catalogs": [{"id": "5116877-12345"}, {"id": "5116877-99999"}]}'


def test_find_category_url_uses_fetch_not_raw_session():
    print("\n[1] _find_category_url must use the WAF-safe _fetch() bridge, "
          "never self._session directly")
    scraper = FakeFetchScraper(fetch_responses=[
        ("/search?q=", SEARCH_RESULTS_HTML),
        ("interactive-panels-with-cpu/search?format=json", CATEGORY_JSON),
    ])
    # Product page fetch (the first self._fetch call inside _find_category_url)
    # needs a title tag to build the search query.
    product_html = '<html><head><title>Buy Some Interactive Panel</title></head></html>'
    scraper._fetch_responses.insert(0, ("p-5116877-12345", product_html))

    result = scraper._find_category_url("https://mkp.gem.gov.in/p-5116877-12345-cat.html", "5116877-12345")

    check("no AssertionError was raised (self._session.get was never called)", True)
    check(f"found the correct category URL (got {result!r})",
          result == "https://mkp.gem.gov.in/interactive-panels-with-cpu/search")
    check(f"all network calls went through _fetch (got {len(scraper._fetch_calls)} calls)",
          len(scraper._fetch_calls) == 3)


def test_cookie_refresh_throttle_engages_across_instances():
    print("\n[2] The cookie-refresh throttle must engage across separate "
          "GeMScraper instances (main.py creates a fresh one per request)")

    # Reset class-level state so this test is independent of import order.
    GeMScraper._last_cookie_refresh_time = None
    GeMScraper._cached_cookies = []

    launch_count = [0]

    class ThrottleTestScraper(GeMScraper):
        def __init__(self):
            self._session = NoNetworkSession()

        def _refresh_session_cookies_with_playwright(self):
            # Patch out the real Playwright launch, but exercise the real
            # throttle/caching logic by calling the real method body via a
            # monkeypatched launch counter.
            return GeMScraper._refresh_session_cookies_with_playwright(self)

    import scraper as scraper_mod

    class FakeContext:
        def cookies(self):
            return [{"name": "sid", "value": "abc", "domain": "mkp.gem.gov.in", "path": "/"}]

    class FakePage:
        def goto(self, *a, **k):
            pass

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

        def close(self):
            pass

    class FakeContextManager:
        def __enter__(self):
            launch_count[0] += 1
            return self

        def __exit__(self, *a):
            return False

        @property
        def chromium(self):
            class _Chromium:
                def launch(self_inner, **k):
                    return FakeBrowser()
            return _Chromium()

    FakeContext.new_page = lambda self: FakePage()

    original_sync_playwright = None
    import playwright.sync_api as sync_api_mod
    original_sync_playwright = sync_api_mod.sync_playwright
    sync_api_mod.sync_playwright = lambda: FakeContextManager()
    try:
        s1 = ThrottleTestScraper()
        s1._refresh_session_cookies_with_playwright()
        s2 = ThrottleTestScraper()  # simulates main.py's fresh-instance-per-request
        s2._refresh_session_cookies_with_playwright()
    finally:
        sync_api_mod.sync_playwright = original_sync_playwright

    check(f"Chromium was only launched once across two instances within the "
          f"throttle window (got {launch_count[0]} launches)", launch_count[0] == 1)
    check(
        f"the second (throttled) instance still received the cached cookies "
        f"(got {len(s2._session.cookies.set_calls)} cookie(s) applied to its session)",
        len(s2._session.cookies.set_calls) == 1,
    )


def test_names_match_short_golden_filter_name():
    print("\n[3] _names_match must match a short real golden-filter name "
          "against a differently-punctuated rendering of the same name")
    scraper = GeMScraper.__new__(GeMScraper)
    check('BIS matches "B.I.S" (short name, differs only in punctuation)',
          scraper._names_match("BIS", "B.I.S"))
    check('BIS matches "bis" (case only)', scraper._names_match("BIS", "bis"))
    check("two genuinely different short names still do NOT match",
          not scraper._names_match("BIS", "ISO"))
    check("two empty/punctuation-only names do NOT match",
          not scraper._names_match("...", "-"))


if __name__ == "__main__":
    test_find_category_url_uses_fetch_not_raw_session()
    test_cookie_refresh_throttle_engages_across_instances()
    test_names_match_short_golden_filter_name()

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
