"""
crawler.py — Playwright-based GeM Category Crawler (async-Playwright backed)

Architecture:
  BrowserManager — runs ONE async_playwright() browser on a single dedicated
                   background thread with its own asyncio event loop. All
                   real browser I/O happens as coroutines there, so many
                   pages can be in flight at once with genuine network
                   overlap (await page.goto() yields control back to the
                   loop while waiting on the network).
  GeMCrawler     — high-level category/product crawling.

Playwright's *sync* API can only be driven from the exact OS thread that
created it — calling page.goto() from a ThreadPoolExecutor worker thread
raises "Cannot switch to a different thread". The async API doesn't have
that restriction as long as everything runs on the loop that owns it, which
is exactly what BrowserManager provides.

Every other module in this app (scraper.py, l1_surpasser.py, chain_hunt.py,
main.py) stays fully synchronous and unaware of any of this: GeMCrawler and
BrowserManager expose plain, thread-safe, *blocking* methods that submit a
coroutine to the background loop (via asyncio.run_coroutine_threadsafe) and
block the calling thread for the result. Callers can keep firing off many
concurrent requests from a ThreadPoolExecutor exactly as before — each one
safely bridges into the shared event loop, where the actual page operations
genuinely interleave instead of serializing or crashing.
"""

import re
import json
import time
import random
import logging
import asyncio
import threading
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

logger = logging.getLogger("gem-crawler")

# Substrings seen in real crashes of the underlying Playwright driver
# connection (e.g. the Chromium process dying mid-session). Playwright's own
# Browser.is_connected() does NOT reliably flip to False for these -- it's
# only updated by an explicit close, not by the transport pipe dying -- so
# BrowserManager tracks this itself instead of trusting is_connected().
_DRIVER_CRASH_SIGNATURES = (
    "Connection closed while reading from the driver",
    "Target page, context or browser has been closed",
    "Browser has been closed",
)


def _is_driver_crash_error(e: Exception) -> bool:
    msg = str(e)
    return any(sig in msg for sig in _DRIVER_CRASH_SIGNATURES)


def _looks_like_login_redirect(current_url: str) -> bool:
    """True if a page navigation landed on GeM's homepage/login instead of
    the requested page -- the signature of an expired/invalid session."""
    final_url = current_url.strip("/")
    return "mkp.gem.gov.in" in final_url and (
        final_url == "https://mkp.gem.gov.in" or "login" in final_url.lower()
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BROWSER MANAGER — async Playwright on a dedicated background event loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BrowserManager:
    """
    Thread-safe singleton owning a persistent async Playwright Chromium
    instance on a dedicated background thread. Exposes a synchronous,
    blocking facade (`run`, `fetch`, `fetch_many`, ...) so the rest of the
    app never has to know or care that Playwright is async underneath.
    """

    _instance = None
    _lock = threading.Lock()

    # Max pages kept warm / in flight at once (also the real concurrency
    # ceiling — GeM's WAF tends to flag bursts above ~8 simultaneous requests)
    _POOL_SIZE = 8

    _VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 720},
    ]

    _USER_AGENTS = [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    ]

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()

        self._playwright = None
        self._browser = None
        self._context = None
        self._initialized = False
        # Set by _fetch_one_async when it observes a driver-crash signature.
        # is_connected() doesn't reliably detect this, so we track it
        # ourselves and force a relaunch on the next _ensure_initialized_async.
        self._crash_detected = False

        # asyncio primitives — must be created on (or after) the loop starts
        self._init_lock: Optional[asyncio.Lock] = None
        self._pool_lock: Optional[asyncio.Lock] = None
        self._page_slots: Optional[asyncio.Semaphore] = None
        self._page_pool: list = []
        self._cookie_refresh_lock: Optional[asyncio.Lock] = None

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        """Get or create the singleton BrowserManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Background event loop lifecycle ───────────────────────────────────

    def _ensure_loop(self):
        """
        Start the dedicated background thread + event loop, once.

        Thread.is_alive() goes True the instant .start() runs — well before
        _run_loop() below has actually assigned self._loop — so a thread
        that only takes the fast path on is_alive() can race ahead of
        initialization and call run_coroutine_threadsafe(coro, None). Every
        caller (fast path or not) must wait on _loop_ready before
        proceeding; the wait is a no-op once it's already set.
        """
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_ready.wait(timeout=10)
            return
        with BrowserManager._lock:
            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_ready.wait(timeout=10)
                return

            self._loop_ready.clear()

            def _run_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._init_lock = asyncio.Lock()
                self._pool_lock = asyncio.Lock()
                self._page_slots = asyncio.Semaphore(self._POOL_SIZE)
                self._cookie_refresh_lock = asyncio.Lock()
                self._loop_ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(
                target=_run_loop, daemon=True, name="playwright-loop"
            )
            self._loop_thread.start()
            self._loop_ready.wait(timeout=10)

    def run(self, coro):
        """
        Thread-safe bridge: submit a coroutine to the background event loop
        and block the calling thread until it completes. Safe to call from
        any thread, including ThreadPoolExecutor workers — this is the only
        supported way to touch Playwright from outside the loop thread.
        """
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    # ── Browser lifecycle (executes ON the background loop) ───────────────

    async def _ensure_initialized_async(self):
        if self._initialized and self._browser and self._browser.is_connected() and not self._crash_detected:
            return

        async with self._init_lock:
            if self._initialized and self._browser and self._browser.is_connected() and not self._crash_detected:
                return

            logger.info("[BrowserManager] Launching Chromium...")
            try:
                from playwright.async_api import async_playwright

                if self._playwright:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                    ],
                )

                viewport = random.choice(self._VIEWPORTS)
                ua = random.choice(self._USER_AGENTS)

                self._context = await self._browser.new_context(
                    viewport=viewport,
                    user_agent=ua,
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                    extra_http_headers={
                        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )

                # Apply stealth: override webdriver detection
                await self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en', 'hi']});
                    window.chrome = {runtime: {}};
                """)

                # Warm up: navigate to GeM homepage to establish cookies.
                # One-time cost at startup, not per-request, so a fixed
                # settle wait here is fine (unlike the old per-fetch sleep).
                page = await self._context.new_page()
                try:
                    await page.goto("https://mkp.gem.gov.in/", timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    cookies = await self._context.cookies()
                    logger.info(f"[BrowserManager] Warmed up. Cookies: {len(cookies)}")
                except Exception as e:
                    logger.warning(f"[BrowserManager] Warmup partial: {e}")
                finally:
                    await page.close()

                async with self._pool_lock:
                    self._page_pool = []
                self._initialized = True
                self._crash_detected = False
                logger.info("[BrowserManager] Chromium ready.")

            except Exception as e:
                logger.error(f"[BrowserManager] Failed to launch: {e}")
                raise RuntimeError(
                    "Playwright browser launch failed. "
                    "Run: pip install playwright && playwright install chromium"
                ) from e

    async def acquire_page_async(self):
        """Acquire a page for one operation, reusing a warm one when available."""
        await self._ensure_initialized_async()
        await self._page_slots.acquire()
        async with self._pool_lock:
            if self._page_pool:
                page = self._page_pool.pop()
                if not page.is_closed():
                    return page
        try:
            return await self._context.new_page()
        except Exception:
            self._page_slots.release()
            raise

    async def release_page_async(self, page):
        """Return a page to the pool for reuse, or close it if the pool is full/dead."""
        try:
            async with self._pool_lock:
                if len(self._page_pool) < self._POOL_SIZE and not page.is_closed():
                    self._page_pool.append(page)
                else:
                    await page.close()
        except Exception:
            pass
        finally:
            self._page_slots.release()

    async def refresh_cookies_async(self):
        await self._ensure_initialized_async()
        # Serialize refreshes: this opens a page outside the _page_slots
        # pool (a refresh can be triggered by a caller that's already
        # holding a slot, so gating it on the same semaphore risks
        # deadlock). The lock instead caps concurrent refreshes to one at
        # a time, so a session expiry hitting many in-flight fetches at
        # once can't spawn an unbounded number of extra pages simultaneously.
        async with self._cookie_refresh_lock:
            page = await self._context.new_page()
            try:
                await page.goto("https://mkp.gem.gov.in/", timeout=30000, wait_until="domcontentloaded")
                cookies = await self._context.cookies()
                logger.info(f"[BrowserManager] Cookies refreshed: {len(cookies)}")
            except Exception as e:
                logger.warning(f"[BrowserManager] Cookie refresh failed: {e}")
            finally:
                await page.close()

    # ── Low-level fetch primitive (used by scraper.py / l1_surpasser.py) ──

    async def _fetch_one_async(self, url: str, timeout: int, retries: int) -> str:
        """
        Fetch a URL, returning its text content. Retries transient failures
        with backoff, refreshes cookies on a redirect-to-login, and — only
        for non-JSON (real HTML) responses — waits briefly for client-side
        content to render. No blind sleep for JSON: it needs no JS
        execution, so domcontentloaded is already enough.
        """
        last_err = None
        for attempt in range(retries):
            page = await self.acquire_page_async()
            try:
                await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                content = await page.content()

                json_match = re.search(r'(\{.*\})', content, re.DOTALL)
                if json_match and ("<pre" in content or "format=json" in url):
                    return json_match.group(1)

                # Detect GeM redirecting us to the homepage/login (session invalid)
                if _looks_like_login_redirect(page.url):
                    if attempt < retries - 1:
                        logger.warning(f"[Crawler] Redirect detected to {page.url}, refreshing session cookies...")
                        await self.refresh_cookies_async()
                        continue
                    # Last attempt: don't return the login page as if it were
                    # valid content -- raise so the caller sees a real failure.
                    raise RuntimeError(f"GeM redirected to login/homepage on final attempt: {page.url}")

                if not json_match:
                    try:
                        await page.wait_for_selector(
                            "h1, #feature_groups, .specifications, #search-result-items",
                            timeout=3000,
                        )
                        content = await page.content()
                    except Exception:
                        pass

                return content
            except Exception as e:
                last_err = e
                logger.warning(f"[Crawler] Fetch attempt {attempt + 1}/{retries} failed for {url}: {e}")
                if _is_driver_crash_error(e):
                    logger.error(
                        "[BrowserManager] Driver crash detected -- marking browser dead "
                        "so the next request forces a relaunch instead of reusing it."
                    )
                    self._crash_detected = True
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
            finally:
                await self.release_page_async(page)
        raise RuntimeError(f"Fetch failed after {retries} attempts: {last_err}")

    def fetch(self, url: str, timeout: int = 30000, retries: int = 3) -> str:
        """Synchronous, thread-safe single-URL fetch. Blocks the caller."""
        return self.run(self._fetch_one_async(url, timeout, retries))

    def fetch_many(self, urls: list, timeout: int = 15000, retries: int = 2) -> list:
        """
        Synchronous, thread-safe multi-URL fetch with GENUINE concurrent
        network I/O (all URLs are in flight on the background loop at once,
        via asyncio.gather). Returns a list aligned with `urls`; failed
        entries are None instead of raising, so one bad page doesn't sink
        the batch.
        """
        async def _gather():
            return await asyncio.gather(
                *(self._fetch_one_async(u, timeout, retries) for u in urls),
                return_exceptions=True,
            )
        results = self.run(_gather())
        return [r if not isinstance(r, Exception) else None for r in results]

    # ── Public sync facade ──────────────────────────────────────────────

    def refresh_cookies(self):
        self.run(self.refresh_cookies_async())

    def shutdown(self):
        """Gracefully close the browser and stop the background loop."""
        if self._loop_thread and self._loop_thread.is_alive():
            async def _shutdown_async():
                try:
                    if self._context:
                        await self._context.close()
                    if self._browser:
                        await self._browser.close()
                    if self._playwright:
                        await self._playwright.stop()
                except Exception:
                    pass

            try:
                self.run(_shutdown_async())
            except Exception:
                pass
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop_thread.join(timeout=5)
            except Exception:
                pass

        self._initialized = False
        self._context = None
        self._browser = None
        self._playwright = None
        self._page_pool = []
        self._loop = None
        self._loop_thread = None
        logger.info("[BrowserManager] Shutdown complete.")

    @property
    def is_alive(self) -> bool:
        return bool(
            self._initialized and self._browser and self._browser.is_connected()
            and not self._crash_detected
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GEM CRAWLER — High-level crawling API (sync facade over the async core)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GeMCrawler:
    """
    GeM category and product page crawler. Every public method here is a
    plain, thread-safe, blocking call — safe to invoke from a
    ThreadPoolExecutor worker, a FastAPI sync route, or anywhere else.
    Internally, work that touches Playwright is defined as a coroutine and
    submitted to BrowserManager's background loop.

    Provides three core methods:
      crawl_category()   — Full category scrape with products + filters
      crawl_product()    — Single product page spec extraction
      crawl_filtered_prices() — Category scrape with golden filters applied
    """

    # All 36 Indian States and Union Territories
    INDIAN_STATES = [
        "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh",
        "Assam", "Bihar", "Chandigarh", "Chhattisgarh",
        "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
        "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
        "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
        "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
        "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
        "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
        "West Bengal",
    ]

    def __init__(self):
        self._bm = BrowserManager.get_instance()

    # ── Category Crawl (JSON-first, Playwright-fallback) ──────────────────────

    def crawl_category(
        self,
        url: str,
        location: str = "",
        max_pages: int = 50,
        extra_filters: Optional[dict] = None,
    ) -> dict:
        """
        Crawl a GeM category listing page.

        Strategy (Hybrid):
          1. Try JSON API first (fast, and now genuinely parallel across pages)
          2. If JSON fails or returns incomplete data, fall back to Playwright DOM extraction
          3. Extract golden filters from facets (API) or sidebar (DOM)
          4. Enrich product specs via product detail pages where needed

        Returns:
        {
            "products": [...],
            "filters": [...],
            "productCount": N,
            "filterCount": N,
            "totalResults": N,
            "url": str,
            "location": str,
            "crawlMethod": "json" | "playwright" | "hybrid",
        }
        """
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        base_url, fragment_params = self._normalize_url(url)
        if extra_filters:
            fragment_params.update(extra_filters)

        # ── Attempt 1: JSON API (fast path) ──────────────────────────────────
        json_result = self._try_json_crawl(base_url, fragment_params, location, max_pages)

        if json_result and json_result.get("products"):
            products = json_result["products"]
            filters = json_result["filters"]

            # Check spec completeness — if > 70% have empty specs, we need Playwright enrichment
            specs_populated = sum(1 for p in products if p.get("specs"))
            spec_ratio = specs_populated / len(products) if products else 0

            if spec_ratio < 0.3 and len(products) > 0:
                logger.info(
                    f"[Crawler] JSON specs sparse ({spec_ratio:.0%}). "
                    f"Enriching top products via Playwright..."
                )
                products = self._enrich_products_playwright(products, filters)
                json_result["products"] = products
                json_result["crawlMethod"] = "hybrid"

            # Rebuild filter values from enriched specs
            if filters:
                filters = self._rebuild_filter_values(products, filters)
                json_result["filters"] = filters
                json_result["filterCount"] = len(filters)

            return json_result

        # ── Attempt 2: Playwright full render (fallback) ─────────────────────
        logger.info("[Crawler] JSON API failed. Falling back to Playwright rendering...")
        return self._playwright_crawl(base_url, fragment_params, location, max_pages)

    # ── Product Detail Crawl ─────────────────────────────────────────────────

    def crawl_product(self, product_url: str) -> dict:
        """Crawl a single product detail page. Extracts full specs from the rendered DOM."""
        try:
            return self._bm.run(self._crawl_product_async(product_url))
        except Exception as e:
            logger.error(f"[Crawler] Product crawl failed for {product_url}: {e}")
            return {"name": "", "price": 0, "specs": {}, "brand": "", "url": product_url}

    async def _crawl_product_async(self, product_url: str) -> dict:
        page = await self._bm.acquire_page_async()
        try:
            await page.goto(product_url, timeout=25000, wait_until="domcontentloaded")

            if _looks_like_login_redirect(page.url):
                logger.warning(
                    f"[Crawler] Product page redirected to login ({page.url}), "
                    "refreshing session cookies and retrying once..."
                )
                await self._bm.refresh_cookies_async()
                await page.goto(product_url, timeout=25000, wait_until="domcontentloaded")
                if _looks_like_login_redirect(page.url):
                    raise RuntimeError(
                        f"GeM redirected to login even after cookie refresh: {page.url}"
                    )

            # Wait for spec tables to load (event-driven — returns as soon
            # as they appear instead of always blocking for a fixed duration)
            try:
                await page.wait_for_selector(
                    "#feature_groups, .specifications, .product-specification", timeout=8000
                )
            except Exception:
                pass

            specs = await self._extract_specs_from_dom_async(page)
            name = ""
            price = 0
            brand = ""

            try:
                name_el = await page.query_selector("h1, .product-name, .product-title")
                if name_el:
                    name = (await name_el.inner_text()).strip()[:150]
            except Exception:
                pass

            try:
                for sel in [".final-price", ".offer_price", ".our_price", "[class*='price']"]:
                    price_el = await page.query_selector(sel)
                    if price_el:
                        price = self._parse_price(await price_el.inner_text()) or 0
                        if price > 0:
                            break
            except Exception:
                pass

            try:
                brand_el = await page.query_selector(".brand-name, [class*='brand']")
                if brand_el:
                    brand = (await brand_el.inner_text()).strip()
            except Exception:
                pass

            return {
                "name": name,
                "price": price,
                "specs": specs,
                "brand": brand,
                "url": product_url,
            }
        finally:
            await self._bm.release_page_async(page)

    # ── Filtered Category Crawl (for chain hunt verification) ────────────────

    def crawl_filtered_prices(
        self,
        url: str,
        filters: dict,
        location: str = "",
        seller_price: Optional[int] = None,
    ) -> dict:
        """
        Fast price-only crawl with filters applied.
        Returns min price, total count, and seller count.
        Used by chain hunt and L1 surpasser for verification.
        """
        try:
            return self._bm.run(self._crawl_filtered_prices_async(url, filters, location))
        except Exception as e:
            logger.error(f"[Crawler] Filtered crawl failed: {e}")
            return {"min_price": None, "total": 0, "product_count": 0, "seller_count": 0, "error": True}

    async def _crawl_filtered_prices_async(self, url: str, filters: dict, location: str) -> dict:
        base_url, fragment_params = self._normalize_url(url)
        fragment_params.update(filters)

        page = await self._bm.acquire_page_async()
        try:
            query_params = {"page": 1, "format": "json", "sort_type": "price_in_asc"}
            for k, v in fragment_params.items():
                if k.lower() not in ("page", "format", "sort_type"):
                    query_params[k] = self._normalize_filter_value(v)
            if location and location.lower() not in ("", "all india", "all"):
                query_params["localized_search"] = location

            api_url = f"{base_url}?{urlencode(query_params)}"
            await page.goto(api_url, timeout=20000, wait_until="domcontentloaded")

            text = await page.content()
            json_match = re.search(r'(\{.*\})', text, re.DOTALL)
            if not json_match:
                return {"min_price": None, "total": 0, "product_count": 0, "seller_count": 0}

            data = json.loads(json_match.group(1))
            total = data.get("number_of_results", 0)
            catalogs = data.get("catalogs", [])

            prices = []
            sellers = set()
            products_out = []
            for cat in catalogs:
                price = int(cat.get("final_price", {}).get("value", 0))
                if price <= 0:
                    continue
                prices.append(price)
                sid = str(cat.get("seller", {}).get("id", ""))
                if sid:
                    sellers.add(sid)
                products_out.append({
                    "id": str(cat.get("id", "")),
                    "name": cat.get("title", ""),
                    "price": price,
                    "seller": cat.get("seller", {}).get("name", ""),
                    "seller_id": sid,
                    "brand": cat.get("brand", ""),
                    "url": self._build_product_url(cat),
                })

            # Fetch page 2 for better seller diversity
            if total > len(catalogs):
                try:
                    query_params["page"] = 2
                    p2_url = f"{base_url}?{urlencode(query_params)}"
                    await page.goto(p2_url, timeout=15000, wait_until="domcontentloaded")
                    text2 = await page.content()
                    json_match2 = re.search(r'(\{.*\})', text2, re.DOTALL)
                    if json_match2:
                        d2 = json.loads(json_match2.group(1))
                        for cat in d2.get("catalogs", []):
                            price = int(cat.get("final_price", {}).get("value", 0))
                            if price <= 0:
                                continue
                            prices.append(price)
                            sid = str(cat.get("seller", {}).get("id", ""))
                            if sid:
                                sellers.add(sid)
                            products_out.append({
                                "id": str(cat.get("id", "")),
                                "name": cat.get("title", ""),
                                "price": price,
                                "seller": cat.get("seller", {}).get("name", ""),
                                "seller_id": sid,
                                "brand": cat.get("brand", ""),
                                "url": self._build_product_url(cat),
                            })
                except Exception:
                    pass

            return {
                "min_price": min(prices) if prices else None,
                "total": total,
                "product_count": len(prices),
                "seller_count": len(sellers),
                "products": products_out,
                "error": False,
            }
        finally:
            await self._bm.release_page_async(page)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL: JSON API Crawl (fast path)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _try_json_crawl(
        self, base_url: str, extra_params: dict, location: str, max_pages: int
    ) -> Optional[dict]:
        """Try to crawl via JSON API. Returns None if JSON is unavailable."""
        try:
            query_params = {"page": 1, "format": "json"}
            for k, v in extra_params.items():
                if k.lower() not in ("page", "format"):
                    query_params[k] = v
            if location and location.lower() not in ("", "all india", "all"):
                query_params["localized_search"] = location

            api_url = f"{base_url}?{urlencode(query_params)}"
            logger.info(f"[Crawler] JSON attempt: {api_url}")

            text1 = self._bm.fetch(api_url)
            if not text1.strip().startswith("{"):
                return None
            data1 = json.loads(text1)

            total_results = data1.get("number_of_results", 0)
            catalogs1 = data1.get("catalogs", [])
            facets = data1.get("facets", {})

            if not catalogs1:
                return None

            per_page = max(len(catalogs1), 10)
            total_pages = max(1, -(-total_results // per_page))
            total_pages = min(total_pages, max_pages)

            # Parse page 1 products
            all_products = []
            for cat in catalogs1:
                p = self._parse_catalog_item(cat)
                if p:
                    all_products.append(p)

            # Fetch remaining pages — GENUINELY concurrent (all in flight on
            # the background event loop at once via asyncio.gather)
            if total_pages > 1:
                page_urls = []
                for pg in range(2, total_pages + 1):
                    params = dict(query_params)
                    params["page"] = pg
                    page_urls.append(f"{base_url}?{urlencode(params)}")

                page_texts = self._bm.fetch_many(page_urls, timeout=15000, retries=2)
                for pg, text in zip(range(2, total_pages + 1), page_texts):
                    if not text or not text.strip().startswith("{"):
                        continue
                    try:
                        pg_data = json.loads(text)
                    except json.JSONDecodeError:
                        logger.warning(f"[Crawler] JSON page {pg}: invalid JSON")
                        continue
                    for cat in pg_data.get("catalogs", []):
                        p = self._parse_catalog_item(cat)
                        if p:
                            all_products.append(p)

            # Parse filters from facets
            filters = self._parse_facets(facets)

            return {
                "products": all_products,
                "filters": filters,
                "productCount": len(all_products),
                "filterCount": len(filters),
                "totalResults": total_results,
                "url": base_url,
                "location": location or "All India",
                "crawlMethod": "json",
            }
        except Exception as e:
            logger.warning(f"[Crawler] JSON crawl failed: {e}")
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL: Playwright Full Render (fallback)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _playwright_crawl(
        self, base_url: str, extra_params: dict, location: str, max_pages: int
    ) -> dict:
        """Full Playwright render-based crawl for when JSON API is unavailable."""
        try:
            return self._bm.run(self._playwright_crawl_async(base_url, extra_params, location))
        except Exception as e:
            logger.error(f"[Crawler] Playwright crawl failed: {e}")
            return {
                "products": [],
                "filters": [],
                "productCount": 0,
                "filterCount": 0,
                "totalResults": 0,
                "url": base_url,
                "location": location or "All India",
                "crawlMethod": "playwright",
                "error": str(e),
            }

    async def _playwright_crawl_async(self, base_url: str, extra_params: dict, location: str) -> dict:
        page = await self._bm.acquire_page_async()
        try:
            url = base_url
            if extra_params:
                qs = urlencode({k: v for k, v in extra_params.items()
                               if k.lower() not in ("format",)})
                if qs:
                    url += "?" + qs

            logger.info(f"[Crawler] Playwright render: {url}")
            await page.goto(url, timeout=30000, wait_until="networkidle")

            if _looks_like_login_redirect(page.url):
                logger.warning(
                    f"[Crawler] Playwright render redirected to login ({page.url}), "
                    "refreshing session cookies and retrying once..."
                )
                await self._bm.refresh_cookies_async()
                await page.goto(url, timeout=30000, wait_until="networkidle")
                if _looks_like_login_redirect(page.url):
                    raise RuntimeError(
                        f"GeM redirected to login even after cookie refresh: {page.url}"
                    )

            products = await self._extract_products_from_dom_async(page)
            filters = await self._extract_filters_from_dom_async(page)

            return {
                "products": products,
                "filters": filters,
                "productCount": len(products),
                "filterCount": len(filters),
                "totalResults": len(products),
                "url": base_url,
                "location": location or "All India",
                "crawlMethod": "playwright",
            }
        finally:
            await self._bm.release_page_async(page)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL: Playwright Enrichment
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_products_playwright(self, products: list, filters: list) -> list:
        """
        Enrich products that have empty specs by visiting their detail pages.
        Only enriches the cheapest 15 products (most relevant for L1 analysis).
        Runs all detail-page visits concurrently via asyncio.gather.
        """
        golden_names = {f["filterName"] for f in filters if f.get("isGolden")}
        to_enrich = []

        for p in sorted(products, key=lambda x: x["price"]):
            if len(to_enrich) >= 15:
                break
            if not p.get("specs") and p.get("productUrl"):
                to_enrich.append(p)
            elif p.get("specs") and golden_names:
                spec_keys_lower = {k.lower() for k in p["specs"].keys()}
                golden_covered = sum(1 for gn in golden_names if gn.lower() in spec_keys_lower)
                if golden_covered < len(golden_names) * 0.3 and p.get("productUrl"):
                    to_enrich.append(p)

        if not to_enrich:
            return products

        logger.info(f"[Crawler] Enriching {len(to_enrich)} products (concurrent)...")

        async def _enrich_all():
            async def enrich_one(product):
                url = product.get("productUrl", "")
                if not url:
                    return product
                try:
                    detail = await self._crawl_product_async(url)
                    if detail.get("specs"):
                        product["specs"] = {**product.get("specs", {}), **detail["specs"]}
                except Exception as e:
                    logger.warning(f"[Crawler] Enrich failed for {url}: {e}")
                return product

            return await asyncio.gather(*(enrich_one(p) for p in to_enrich), return_exceptions=True)

        try:
            self._bm.run(_enrich_all())
        except Exception as e:
            logger.warning(f"[Crawler] Enrichment batch failed: {e}")

        return products

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DOM EXTRACTION HELPERS (async — run on the background loop)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _extract_products_from_dom_async(self, page) -> list:
        """Extract products from the fully rendered category page DOM."""
        products = []

        cards = await page.query_selector_all(
            "#search-result-items li, "
            ".product-wrapper, .catalog-item, .product-card, "
            ".product-item, .product_card, .product-tuple, "
            ".product-grid-item"
        )

        if not cards:
            links = await page.query_selector_all("a[href*='/p-']")
            seen = set()
            card_candidates = []
            for link in links:
                href = await link.get_attribute("href") or ""
                if re.search(r'/p-\d+-\d+-cat\.html', href):
                    parent = await link.evaluate_handle(
                        "el => el.closest('li, div.product-card, div[class*=product]') || el.parentElement.parentElement"
                    )
                    parent_el = parent.as_element()
                    if parent_el:
                        key = await parent_el.evaluate("el => el.outerHTML.substring(0, 100)")
                        if key not in seen:
                            seen.add(key)
                            card_candidates.append(parent_el)
            cards = card_candidates

        for card in cards:
            try:
                link_el = await card.query_selector("a[href*='/p-']")
                if not link_el:
                    continue

                href = await link_el.get_attribute("href") or ""
                product_url = href if href.startswith("http") else f"https://mkp.gem.gov.in{href}"

                m = re.search(r'/p-(\d+)-(\d+)-cat\.html', product_url)
                if not m:
                    continue

                variant_id = f"{m.group(1)}-{m.group(2)}"

                name_el = await card.query_selector(".product-title, .title, .product-name, h5, h4, [class*='title']")
                if not name_el:
                    name_el = link_el
                name = ((await name_el.inner_text()) if name_el else "").strip()[:150]

                price = 0
                price_el = await card.query_selector(".final-price, .price, .offer_price, [class*='price']")
                if price_el:
                    price = self._parse_price(await price_el.inner_text()) or 0
                if price <= 0:
                    continue

                brand_el = await card.query_selector(".brand, .brand-name, [class*='brand']")
                brand = ((await brand_el.inner_text()) if brand_el else "").strip()

                seller_el = await card.query_selector(".seller-name, .seller, [class*='seller']")
                seller = ((await seller_el.inner_text()) if seller_el else "").strip()

                products.append({
                    "id": variant_id,
                    "name": name,
                    "price": price,
                    "brand": brand,
                    "seller": seller,
                    "sellerType": "",
                    "productUrl": product_url,
                    "specs": {},
                })
            except Exception as e:
                logger.warning(f"[Crawler] DOM card parse error: {e}")
                continue

        return products

    async def _extract_filters_from_dom_async(self, page) -> list:
        """Extract golden filters from the rendered sidebar."""
        filters = []

        sidebar = await page.query_selector(
            "#facets, #filters, .facets-container, .sidebar, "
            "#search-facets, .filter-sidebar"
        )
        if not sidebar:
            return filters

        facet_blocks = await sidebar.query_selector_all(
            ".facet, .filter-section, .facet-list, [class*='filter-group']"
        )

        for block in facet_blocks:
            try:
                title_el = await block.query_selector("h5, h6, .facet-title, [class*='title']")
                if not title_el:
                    continue
                filter_name = (await title_el.inner_text()).strip().replace(":", "")
                if not filter_name or len(filter_name) > 80:
                    continue

                classes = await block.get_attribute("class") or ""
                is_golden = "golden" in classes.lower()
                if not is_golden:
                    title_classes = await title_el.get_attribute("class") or ""
                    is_golden = "golden" in title_classes.lower()
                if not is_golden:
                    name_lower = filter_name.lower()
                    is_golden = any(k in name_lower for k in ("make in india", "mse", "startup", "pac"))

                filter_key = await block.get_attribute("id") or await block.get_attribute("data-facet") or self._to_key(filter_name)
                vals = []
                val_elements = await block.query_selector_all("label, .facet-values li, [class*='option']")
                for vel in val_elements:
                    val_text = (await vel.inner_text()).strip()
                    val_text = re.sub(r'\s*\(\d+\)\s*$', '', val_text).strip()
                    if val_text and val_text.lower() not in ("true", "false", "null", "all", ""):
                        if val_text not in vals:
                            vals.append(val_text)

                if not vals:
                    continue

                filters.append({
                    "filterName": filter_name,
                    "filterKey": filter_key,
                    "values": vals[:20],
                    "isGolden": is_golden,
                    "type": "spec" if not is_golden else "golden",
                })
            except Exception as e:
                logger.warning(f"[Crawler] Filter block parse error: {e}")
                continue

        return filters

    async def _extract_specs_from_dom_async(self, page) -> dict:
        """Extract all specifications from a rendered product detail page."""
        specs = {}

        # Method 1: Feature groups table
        try:
            feature_groups = await page.query_selector("#feature_groups")
            if feature_groups:
                rows = await feature_groups.query_selector_all("tr")
                for row in rows:
                    cells = await row.query_selector_all("td, th")
                    if len(cells) >= 2:
                        name = (await cells[0].inner_text()).strip()
                        value = (await cells[1].inner_text()).strip()
                        if name and value and len(value) < 200:
                            specs[name] = value
        except Exception:
            pass

        # Method 2: Specifications div
        try:
            specs_div = await page.query_selector(".specifications, .product-specification")
            if specs_div:
                params = await specs_div.query_selector_all(".param-container, .spec-row, tr")
                for param in params:
                    key_el = await param.query_selector(".key_name, .spec-name, td:first-child")
                    val_el = await param.query_selector(".key_value, .spec-value, td:nth-child(2)")
                    if key_el and val_el:
                        name = (await key_el.inner_text()).strip()
                        value = (await val_el.inner_text()).strip()
                        if name and value and name not in specs and len(value) < 200:
                            specs[name] = value
        except Exception:
            pass

        # Method 3: Generic key-value divs
        try:
            kv_rows = await page.query_selector_all("[class*='specification'] [class*='row'], [class*='spec'] [class*='row']")
            for row in kv_rows:
                children = await row.query_selector_all("div, span, td")
                if len(children) >= 2:
                    name = (await children[0].inner_text()).strip()
                    value = (await children[1].inner_text()).strip()
                    if name and value and name not in specs and len(value) < 200:
                        specs[name] = value
        except Exception:
            pass

        return specs

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CATALOG/FACET PARSING (pure Python — no Playwright involved)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _parse_catalog_item(self, cat: dict) -> Optional[dict]:
        """Parse a single catalog JSON item into a normalized product dict."""
        price = int(cat.get("final_price", {}).get("value", 0))
        if price <= 0:
            return None

        specs = {}
        for key in ("specifications", "product_specifications", "spec_params",
                     "params", "attributes", "properties", "features"):
            items = cat.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        name = (item.get("name") or item.get("key") or
                                item.get("label") or item.get("param_name") or "")
                        value = (item.get("value") or item.get("val") or
                                 item.get("param_value") or "")
                        if name and value and len(str(value)) < 200:
                            specs[str(name).strip()] = str(value).strip()
            elif isinstance(items, dict):
                for name, value in items.items():
                    if name and value and len(str(value)) < 200:
                        specs[str(name).strip()] = str(value).strip()

        return {
            "id": str(cat.get("id", "")),
            "catalogue_id": str(cat.get("id", "")),
            "name": cat.get("title", ""),
            "price": price,
            "brand": cat.get("brand", ""),
            "seller": cat.get("seller", {}).get("name", ""),
            "seller_name": cat.get("seller", {}).get("name", ""),
            "seller_id": str(cat.get("seller", {}).get("id", "")),
            "sellerType": cat.get("seller", {}).get("display_sold_as", ""),
            "rating": cat.get("seller", {}).get("rating", ""),
            "listPrice": int(cat.get("list_price", {}).get("value", 0)),
            "discount": cat.get("discount_percent", 0),
            "imgUrl": cat.get("img_url", ""),
            "productUrl": self._build_product_url(cat),
            "oem_id": str(cat.get("oem_id", "")),
            "specs": specs,
        }

    def _build_product_url(self, catalog: dict) -> str:
        """Build a full product URL from catalog data."""
        url_parts = catalog.get("url", [])
        if url_parts and len(url_parts) >= 3:
            return f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"
        return ""

    def _parse_facets(self, facets: dict) -> list:
        """Parse facets JSON into a list of filter definitions."""
        filters = []

        spec_facets = facets.get("product specifications", {}).get("facet_list", [])
        for facet in spec_facets:
            name = facet.get("name", "")
            code = facet.get("code", "")
            css_class = facet.get("css_class", "")
            if len(name) > 200 or not code:
                continue

            values = self._pull_facet_values(facet)
            filters.append({
                "filterName": name,
                "filterKey": code,
                "isGolden": css_class == "golden",
                "values": values[:20],
                "type": facet.get("type", ""),
            })

        admin_facets = facets.get("administrative", {}).get("facet_list", [])
        for facet in admin_facets:
            name = facet.get("name", "")
            code = facet.get("code", "")
            name_lower = name.lower()
            is_golden = any(k in name_lower for k in ("make in india", "mse", "startup", "pac"))
            if is_golden or name in ("Make in India", "Lead Time for Dispatch"):
                values = self._pull_facet_values(facet)
                filters.append({
                    "filterName": name,
                    "filterKey": code,
                    "isGolden": is_golden,
                    "values": values[:20],
                    "type": facet.get("type", ""),
                })

        return filters

    def _pull_facet_values(self, facet: dict) -> list:
        """Extract option values from a facet entry."""
        for key in ("facet_values", "topValues", "top_values", "values",
                     "entries", "options", "items", "terms"):
            raw = facet.get(key, [])
            if not raw:
                continue
            vals = []
            for v in raw:
                if isinstance(v, dict):
                    label = (v.get("name") or v.get("value") or
                             v.get("code") or v.get("label") or "")
                else:
                    label = str(v)
                label = str(label).strip()
                if label and label.lower() not in ("true", "false", "null", ""):
                    vals.append(label)
            if vals:
                return vals
        return []

    def _rebuild_filter_values(self, products: list, filters: list) -> list:
        """Rebuild filter values from enriched product specs."""
        for product in products:
            for spec_name, spec_value in product.get("specs", {}).items():
                if not spec_value or len(spec_value) > 150:
                    continue
                for f in filters:
                    if self._names_match(spec_name, f["filterName"]):
                        if spec_value not in f["values"]:
                            f["values"].append(spec_value)
                        break

        # Remove filters with no values
        return [f for f in filters if f.get("values")]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UTILITIES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _normalize_url(self, url: str) -> tuple:
        """Normalize a GeM URL: extract base URL and fragment/query params."""
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        parsed = urlparse(url)
        extra_params = {}

        # Parse fragment-based query params
        if parsed.fragment:
            frag = parsed.fragment
            if frag.startswith("/?"):
                frag_qs = frag[2:]
            elif frag.startswith("?"):
                frag_qs = frag[1:]
            elif "?" in frag:
                frag_qs = frag.split("?", 1)[1]
            else:
                frag_qs = frag
            frag_params = parse_qs(frag_qs, keep_blank_values=True)
            for k, v_list in frag_params.items():
                extra_params[k] = v_list[0] if len(v_list) == 1 else v_list

        # Parse standard query params
        if parsed.query:
            std_params = parse_qs(parsed.query, keep_blank_values=True)
            for k, v_list in std_params.items():
                if k.lower() not in ("format", "page"):
                    extra_params[k] = v_list[0] if len(v_list) == 1 else v_list

        clean_url = parsed._replace(fragment="", query="").geturl()
        if not clean_url.endswith("/search"):
            clean_url = clean_url.rstrip("/")

        return clean_url, extra_params

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two spec/filter names are equivalent."""
        n1 = name1.lower().strip().replace("::", "/")
        n2 = name2.lower().strip().replace("::", "/")
        if n1 == n2:
            return True
        k1 = re.sub(r'[^a-z0-9]', '', n1)
        k2 = re.sub(r'[^a-z0-9]', '', n2)
        return k1 == k2 and len(k1) > 5

    def _parse_price(self, text: str) -> Optional[int]:
        """Parse a price string into an integer."""
        cleaned = re.sub(r'[₹,\s]', '', text)
        cleaned = re.sub(r'(?i)INR|Rs\.?', '', cleaned)
        m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if m:
            val = float(m.group(1))
            if 10 <= val <= 10_000_000:
                return int(val)
        return None

    def _to_key(self, name: str) -> str:
        """Convert a human-readable name to a filter key."""
        key = re.sub(r'[^a-z0-9\s]', '', name.lower().strip())
        return re.sub(r'\s+', '_', key).strip('_')[:40]

    def _normalize_filter_value(self, val) -> str:
        """Normalize a spec filter value for the GeM search API."""
        if not isinstance(val, str):
            return str(val)
        if "/" in val:
            val = val.split("/")[0]
        val = val.replace(" ", "").replace(":", "")
        return val
