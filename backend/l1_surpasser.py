"""
l1_surpasser.py — Hardened L1 Chain Surpasser Engine

Production-grade GeM (gem.gov.in) scraping and sequential L1 elimination.

Architecture:
  GeMCategoryScraper — full paginated scrape with 7 failure mode defenses
  GeMFilterScraper   — live golden filter option extraction from facets
  L1ChainSurpasser   — greedy-sequential elimination loop

All network calls use exponential backoff (base 1s, max 32s, 5 retries).
Global concurrency is capped at 8 simultaneous HTTP requests via semaphore.

Usage:
  python l1_surpasser.py <category_url> <my_catalogue_id> <my_price>
"""

import re
import json
import math
import time
import logging
import itertools
import threading
import requests
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("l1-surpasser")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EXCEPTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DataInstabilityError(Exception):
    """Raised when total_count changes between page fetches after max restarts."""
    pass


class IncompleteScrapeError(Exception):
    """Raised when scraped products < 95% of total_count after max retries."""
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

# Global semaphore: no more than 8 concurrent HTTP requests to GeM anywhere
_HTTP_SEMAPHORE = threading.BoundedSemaphore(8)

# Backoff constants
_BACKOFF_BASE = 1      # seconds
_BACKOFF_MAX = 32      # seconds
_MAX_FETCH_RETRIES = 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _clean_category_url(url: str) -> str:
    """Normalize a GeM URL: strip fragments, query params, ensure https."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # Handle fragment-based query strings (search#/?q=XXX)
    base = url.split("#")[0].split("?")[0]
    if not base.endswith("/search"):
        base = base.rstrip("/")
    return base


def _extract_fragment_params(url: str) -> dict:
    """Extract query params from fragment-based URLs (search#/?q=XXX&...)."""
    parsed = urlparse(url.strip())
    extra = {}
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
            extra[k] = v_list[0] if len(v_list) == 1 else v_list
    return extra


_COOKIE_LOCK = threading.Lock()
_last_cookie_refresh_time = 0.0

def _refresh_session_cookies_with_playwright(session: requests.Session) -> bool:
    """Launch headless Playwright browser to establish valid session cookies on GeM."""
    global _last_cookie_refresh_time
    with _COOKIE_LOCK:
        now = time.time()
        if now - _last_cookie_refresh_time < 30:
            logger.info("[Playwright] Cookies were refreshed recently, skipping redundant refresh.")
            return True
            
        logger.info("[Playwright] Refreshing session cookies via headless Chromium...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=_HEADERS["User-Agent"]
                )
                page = context.new_page()
                page.goto("https://mkp.gem.gov.in/", timeout=30000)
                
                # Extract cookies
                cookies = context.cookies()
                browser.close()
                
            # Clear current cookies and inject the new ones
            session.cookies.clear()
            for cookie in cookies:
                session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie["domain"],
                    path=cookie["path"]
                )
            _last_cookie_refresh_time = now
            logger.info(f"[Playwright] Successfully loaded {len(cookies)} cookies into requests session.")
            return True
        except Exception as e:
            logger.error(f"[Playwright] Failed to refresh cookies: {e}")
            return False


def _fetch_with_backoff(session: requests.Session, url: str) -> str:
    """
    Fetch a URL with exponential backoff.
    Base 1s, max 32s, max 5 retries.
    Raises RuntimeError after all retries exhausted.
    """
    last_err = None
    for attempt in range(_MAX_FETCH_RETRIES):
        try:
            with _HTTP_SEMAPHORE:
                resp = session.get(url, timeout=20, allow_redirects=True)

            # Detect GeM session redirect (homepage/login)
            if "mkp.gem.gov.in" in resp.url:
                final = resp.url.strip("/")
                if final == "https://mkp.gem.gov.in" or "login" in resp.url.lower():
                    if attempt < _MAX_FETCH_RETRIES - 1:
                        logger.warning(f"[Scraper] Redirect detected to {resp.url}, refreshing session cookies...")
                        _refresh_session_cookies_with_playwright(session)
                        continue

            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_err = e
            # If we hit a 403 Forbidden or 401 Unauthorized, refresh the session cookies immediately
            is_auth_error = isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code in (401, 403)
            if is_auth_error and attempt < _MAX_FETCH_RETRIES - 1:
                logger.warning(f"[Scraper] HTTP {e.response.status_code} detected, refreshing session cookies via Playwright...")
                _refresh_session_cookies_with_playwright(session)
                time.sleep(2)
                continue

            if attempt < _MAX_FETCH_RETRIES - 1:
                backoff = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
                time.sleep(backoff)

    raise RuntimeError(f"Failed after {_MAX_FETCH_RETRIES} attempts: {last_err}")


def _names_match(name1: str, name2: str) -> bool:
    """Check if two spec/filter names are semantically equivalent."""
    n1 = name1.lower().strip().replace("::", "/")
    n2 = name2.lower().strip().replace("::", "/")
    if n1 == n2:
        return True
    k1 = re.sub(r'[^a-z0-9]', '', n1)
    k2 = re.sub(r'[^a-z0-9]', '', n2)
    return k1 == k2 and len(k1) > 5


def _create_session() -> requests.Session:
    """Create a requests.Session with retry strategy and browser headers."""
    session = requests.Session()
    session.headers.update(_HEADERS)

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Establish initial cookies (JSESSIONID etc.) via Playwright
    _refresh_session_cookies_with_playwright(session)

    return session


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASS 1: GeMCategoryScraper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GeMCategoryScraper:
    """
    Full category scraper with all 7 failure modes handled:

      1. Offset Drift     — monitor total_count per page, restart if changed
      2. Incomplete Scrape — assert len(deduped) >= total_count * 0.95
      3. Sort Order        — enforce sort=price_asc on every request
      4. Duplicates        — deduplicate by catalogue_id, keep lowest price
      5. Boundary Pages    — empty last page = valid termination, not error
      6. My Product Rank   — locate my_catalogue_id and record 1-indexed rank
      7. Filter Count      — re-derive total_pages from each response's total_count
    """

    MAX_RESTARTS = 3
    COMPLETENESS_THRESHOLD = 0.95
    MAX_SCRAPE_ATTEMPTS = 3
    MAX_PAGES = 500  # absolute safety cap

    def __init__(
        self,
        session: requests.Session,
        category_url: str,
        active_filters: Optional[dict] = None,
        my_catalogue_id: str = "",
        fragment_params: Optional[dict] = None,
        max_price: Optional[int] = None,
    ):
        self._session = session
        self._base_url = _clean_category_url(category_url)
        self._active_filters = dict(active_filters or {})
        self._my_catalogue_id = str(my_catalogue_id)
        self._fragment_params = dict(fragment_params or {})
        self._max_price = max_price
        self._early_stopped = False

    # ── URL building ─────────────────────────────────────────────────────────

    def _build_page_url(self, page: int) -> str:
        """Build a fully-qualified page URL with sort order and active filters."""
        params = {"page": page, "format": "json"}
        # Failure Mode 3: always enforce price ascending sort
        # GeM uses different sort param names; we try the most common one.
        # If it doesn't work, products will still be sorted client-side.
        params["sort_type"] = "price_in_asc"

        # Merge fragment params (from URLs like search#/?q=chair)
        for k, v in self._fragment_params.items():
            if k.lower() not in ("page", "format"):
                params[k] = v

        # Merge active golden filters
        params.update(self._active_filters)

        return f"{self._base_url}?{urlencode(params)}"

    # ── Single page fetch ────────────────────────────────────────────────────

    def _fetch_page(self, page: int) -> dict:
        """Fetch a single JSON page with exponential backoff."""
        url = self._build_page_url(page)
        text = _fetch_with_backoff(self._session, url).strip()

        if not text.startswith("{"):
            raise ValueError(f"Non-JSON response from page {page} (got HTML/empty)", text)

        return json.loads(text)

    # ── Product parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_product(cat: dict) -> Optional[dict]:
        """Parse a single catalog JSON item into a normalized product dict."""
        price = int(cat.get("final_price", {}).get("value", 0))
        if price <= 0:
            return None

        catalogue_id = str(cat.get("id", ""))
        seller_info = cat.get("seller", {})

        # Build product URL from the url parts array
        url_parts = cat.get("url", [])
        product_url = ""
        if url_parts and len(url_parts) >= 3:
            product_url = f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"

        # Extract inline golden_params from all possible spec fields
        golden_params = {}
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
                            golden_params[str(name).strip()] = str(value).strip()
            elif isinstance(items, dict):
                for name, value in items.items():
                    if name and value and len(str(value)) < 200:
                        golden_params[str(name).strip()] = str(value).strip()

        return {
            "catalogue_id": catalogue_id,
            "price": price,
            "name": cat.get("title", ""),
            "brand": cat.get("brand", ""),
            "seller_id": str(seller_info.get("id", "")),
            "seller_name": seller_info.get("name", ""),
            "oem_id": str(cat.get("oem_id", "")),
            "product_url": product_url,
            "golden_params": golden_params,
        }

    # ── Deduplication ────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(products: list) -> list:
        """
        Failure Mode 4: Deduplicate by catalogue_id.
        Keep the lowest-priced entry per duplicate group.
        """
        seen: dict = {}
        for p in products:
            cid = p["catalogue_id"]
            if cid not in seen or p["price"] < seen[cid]["price"]:
                seen[cid] = p
        return list(seen.values())

    # ── Main scrape entry point ──────────────────────────────────────────────

    def scrape(self) -> dict:
        """
        Full category scrape. Returns:
        {
            "products": [...],       # sorted price asc, deduplicated
            "total_count": N,
            "my_product_rank": M,    # 1-indexed, or None
            "my_product": {...},     # or None
            "scrape_stats": {
                "pages_fetched": P,
                "duplicates_removed": D,
                "restarts": R,
                "pagination_mode": "offset"
            }
        }
        """
        stats = {
            "pages_fetched": 0,
            "duplicates_removed": 0,
            "restarts": 0,
            "pagination_mode": "offset",
        }

        products = []
        for attempt in range(self.MAX_SCRAPE_ATTEMPTS):
            try:
                products, stats = self._execute_full_scrape(stats)

                # Failure Mode 2: completeness check
                tc = stats.get("total_count", 0)
                # Skip completeness check if we stopped early due to max_price
                if tc > 0 and not self._early_stopped:
                    ratio = len(products) / tc
                    if ratio < self.COMPLETENESS_THRESHOLD:
                        if attempt < self.MAX_SCRAPE_ATTEMPTS - 1:
                            logger.warning(
                                f"[Scraper] Incomplete: {len(products)}/{tc} "
                                f"({ratio:.1%}). Retry {attempt + 1}..."
                            )
                            time.sleep(2)
                            stats["restarts"] += 1
                            continue
                        raise IncompleteScrapeError(
                            f"Only scraped {len(products)}/{tc} products "
                            f"({ratio:.1%}) after {self.MAX_SCRAPE_ATTEMPTS} attempts"
                        )
                break  # success

            except DataInstabilityError:
                if attempt < self.MAX_SCRAPE_ATTEMPTS - 1:
                    logger.warning("[Scraper] Data instability, retrying...")
                    time.sleep(3)
                    stats["restarts"] += 1
                    continue
                raise

        # Failure Mode 3: enforce price sort client-side regardless of API
        products.sort(key=lambda p: p["price"])

        # Failure Mode 6: locate my product and record rank
        my_product = None
        my_product_rank = None
        for i, p in enumerate(products):
            if self._my_catalogue_id and self._my_catalogue_id in p["catalogue_id"]:
                my_product = p
                my_product_rank = i + 1  # 1-indexed
                break

        return {
            "products": products,
            "total_count": stats.get("total_count", len(products)),
            "my_product_rank": my_product_rank,
            "my_product": my_product,
            "scrape_stats": stats,
        }

    # ── Internal paginated scrape with drift detection ───────────────────────

    def _execute_full_scrape(self, stats: dict) -> tuple:
        """
        Walk all pages with offset-drift detection.
        Returns (deduplicated_products, updated_stats).
        """
        # ── Page 1 ───────────────────────────────────────────────────────────
        try:
            data1 = self._fetch_page(1)
            is_html = False
        except ValueError as e:
            if len(e.args) >= 2 and isinstance(e.args[1], str):
                html_text = e.args[1]
                is_html = True
            else:
                raise

        if is_html:
            return self._scrape_html_fallback(html_text, stats)

        stats["pages_fetched"] += 1

        total_count = data1.get("number_of_results", 0)
        stats["total_count"] = total_count

        catalogs = data1.get("catalogs", [])
        per_page = max(len(catalogs), 10)

        # Store raw facets for filter extraction (used by GeMFilterScraper)
        stats["_raw_facets"] = data1.get("facets", {})

        all_raw: list = []
        page1_prices = []
        for cat in catalogs:
            p = self._parse_product(cat)
            if p:
                all_raw.append(p)
                page1_prices.append(p["price"])

        # Early stopping check on Page 1
        if self._max_price is not None and page1_prices:
            if min(page1_prices) > self._max_price:
                self._early_stopped = True
                logger.info(
                    f"[Scraper] Early stopping on Page 1 because minimum price "
                    f"Rs. {min(page1_prices):,} exceeds max_price Rs. {self._max_price:,}"
                )
                products = self._deduplicate(all_raw)
                stats["duplicates_removed"] = len(all_raw) - len(products)
                return products, stats

        if total_count == 0 or not catalogs:
            stats["total_count"] = total_count
            return [], stats

        # Failure Mode 7: derive total_pages fresh
        total_pages = max(1, math.ceil(total_count / per_page))
        total_pages = min(total_pages, self.MAX_PAGES)

        if total_pages <= 1:
            products = self._deduplicate(all_raw)
            stats["duplicates_removed"] = len(all_raw) - len(products)
            return products, stats

        # ── Remaining pages with drift detection ─────────────────────────────
        restart_count = 0
        page = 2

        while page <= total_pages:
            if restart_count > self.MAX_RESTARTS:
                raise DataInstabilityError(
                    f"total_count changed {restart_count} times during scrape "
                    f"(drift: {total_count} products)"
                )

            try:
                data = self._fetch_page(page)
                stats["pages_fetched"] += 1
            except Exception as e:
                logger.warning(f"[Scraper] Page {page} fetch failed: {e}")
                # Failure Mode 5: last page failing is acceptable termination
                if page >= total_pages:
                    break
                page += 1
                continue

            # Failure Mode 1: Offset drift detection
            new_total = data.get("number_of_results", total_count)
            if new_total != total_count:
                logger.warning(
                    f"[Scraper] DRIFT: total {total_count} -> {new_total} "
                    f"at page {page}. Restart #{restart_count + 1}."
                )
                restart_count += 1
                stats["restarts"] = restart_count

                # Full restart from page 1
                all_raw.clear()
                data1 = self._fetch_page(1)
                stats["pages_fetched"] += 1
                total_count = data1.get("number_of_results", total_count)
                stats["total_count"] = total_count
                stats["_raw_facets"] = data1.get("facets", {})

                for cat in data1.get("catalogs", []):
                    p = self._parse_product(cat)
                    if p:
                        all_raw.append(p)

                per_page_new = max(len(data1.get("catalogs", [])), 10)
                total_pages = max(1, math.ceil(total_count / per_page_new))
                total_pages = min(total_pages, self.MAX_PAGES)
                page = 2
                continue

            page_catalogs = data.get("catalogs", [])

            # Failure Mode 5: empty page = end of data (not an error)
            if not page_catalogs:
                break

            current_page_prices = []
            for cat in page_catalogs:
                p = self._parse_product(cat)
                if p:
                    all_raw.append(p)
                    current_page_prices.append(p["price"])

            # Early stopping check in pagination loop
            if self._max_price is not None and current_page_prices:
                if min(current_page_prices) > self._max_price:
                    self._early_stopped = True
                    logger.info(
                        f"[Scraper] Early stopping at page {page} because minimum page price "
                        f"Rs. {min(current_page_prices):,} exceeds max_price Rs. {self._max_price:,}"
                    )
                    break

            page += 1

        # Failure Mode 4: deduplicate
        products = self._deduplicate(all_raw)
        stats["duplicates_removed"] = len(all_raw) - len(products)

        return products, stats

    def _scrape_html_fallback(self, html_text: str, stats: dict) -> tuple:
        from bs4 import BeautifulSoup
        import re
        soup = BeautifulSoup(html_text, "html.parser")
        
        products = []
        cards = soup.select(
            "#search-result-items li, "
            ".product-wrapper, "
            ".catalog-item, "
            ".product-card, "
            ".product-item, "
            ".product_card, "
            ".product-tuple, "
            ".product-grid-item"
        )
        
        if not cards:
            links = soup.find_all("a", href=re.compile(r'/p-\d+-\d+-cat\.html'))
            seen_parents = set()
            for a in links:
                p = a.parent
                for _ in range(4):
                    if p and p.name in ('div', 'li') and (p.get('class') or p.name == 'li'):
                        if p not in seen_parents:
                            seen_parents.add(p)
                            cards.append(p)
                        break
                    p = p.parent if p else None

        for card in cards:
            try:
                link_el = card.select_one('a[href*="/p-"]')
                if not link_el:
                    link_el = card.find('a', href=re.compile(r'/p-\d+-\d+-cat\.html'))
                if not link_el:
                    continue
                
                href = link_el.get("href", "")
                product_url = href if href.startswith("http") else f"https://mkp.gem.gov.in{href}"
                
                m = re.search(r'/p-(\d+)-(\d+)-cat\.html', product_url)
                if m:
                    catalog_id = m.group(1)
                    variant_id = f"{catalog_id}-{m.group(2)}"
                else:
                    continue

                name_el = card.select_one('.product-title, .title, .product-name, h5, h4, [class*="title"]')
                if not name_el:
                    name_el = link_el
                name = name_el.get_text(strip=True) if name_el else ""
                name = re.sub(r'([A-Z\s]+)\1', r'\1', name).strip()
                
                price = 0
                price_el = card.select_one('.final-price, .price, .offer_price, .our_price, [class*="price"]')
                if price_el:
                    price = self._parse_price_text(price_el.get_text(strip=True)) or 0

                if price <= 0:
                    continue

                brand_el = card.select_one('.brand, .brand-name, [class*="brand"]')
                brand = brand_el.get_text(strip=True) if brand_el else ""
                
                seller_el = card.select_one('.seller-name, .seller, .sold-by')
                if not seller_el:
                    seller_el = card.select_one('[class*="seller-name"], [class*="sold-by"]')
                seller = seller_el.get_text(strip=True) if seller_el else ""
                
                # Specs
                golden_params = {}
                for li in card.select('ul.specs-list li, .specs li, .specifications li, .attributes li'):
                    text = li.get_text(strip=True)
                    if ":" in text:
                        k, v = text.split(":", 1)
                        golden_params[k.strip()] = v.strip()

                products.append({
                    "catalogue_id": variant_id,
                    "price": price,
                    "name": name,
                    "brand": brand,
                    "seller_id": "",
                    "seller_name": seller,
                    "oem_id": "",
                    "product_url": product_url,
                    "golden_params": golden_params,
                })
            except Exception as e:
                logger.warning(f"[HTML Fallback] Error parsing card: {e}")
                continue

        # Extract facets
        raw_facets = {"product specifications": {"facet_list": []}, "administrative": {"facet_list": []}}
        sidebar = soup.select_one('#facets, #filters, .facets-container, .sidebar, #search-facets, .filter-sidebar')
        if sidebar:
            facet_blocks = sidebar.select('.facet, .filter-section, .facet-list, [class*="filter-group"]')
            for block in facet_blocks:
                title_el = block.select_one('h5, h6, .facet-title, [class*="title"]')
                if not title_el:
                    continue
                filter_name = title_el.get_text(strip=True).replace(":", "").strip()
                if not filter_name or len(filter_name) > 80:
                    continue
                
                filter_key = block.get('id') or block.get('data-facet') or self._to_key(filter_name)
                
                # Extract options
                vals = []
                val_elements = block.select('label, .facet-values li, [class*="option"], [class*="value"]')
                leaf_elements = []
                for el in val_elements:
                    is_parent = False
                    for other in val_elements:
                        if other is not el and other in el.descendants:
                            is_parent = True
                            break
                    if not is_parent:
                        leaf_elements.append(el)
                        
                for val_el in leaf_elements:
                    val_text = val_el.get_text(strip=True)
                    val_text = re.sub(r'\s*\(\d+\)\s*$', '', val_text).strip()
                    if val_text and val_text.lower() not in ("true", "false", "null", "all", ""):
                        if val_text not in vals:
                            vals.append(val_text)
                
                if not vals:
                    continue
                
                is_golden = 'golden' in block.get('class', []) or 'golden' in title_el.get('class', [])
                if not is_golden:
                    name_lower = filter_name.lower()
                    is_golden = any(k in name_lower for k in ("make in india", "mse", "startup", "pac"))
                
                # Map back to facet structure
                facet_entry = {
                    "name": filter_name,
                    "code": filter_key,
                    "css_class": "golden" if is_golden else "",
                    "type": "spec",
                    "facet_values": [{"name": v, "value": v} for v in vals]
                }
                if is_golden:
                    raw_facets["product specifications"]["facet_list"].append(facet_entry)
                else:
                    raw_facets["administrative"]["facet_list"].append(facet_entry)

        # Fallback dummy golden parameters from specs
        if not raw_facets["product specifications"]["facet_list"] and products:
            filter_values = {}
            for p in products:
                for k, v in p.get("golden_params", {}).items():
                    filter_values.setdefault(k, set()).add(v)
            for fname, vals in filter_values.items():
                raw_facets["product specifications"]["facet_list"].append({
                    "name": fname,
                    "code": self._to_key(fname),
                    "css_class": "golden",
                    "type": "spec",
                    "facet_values": [{"name": v, "value": v} for v in sorted(list(vals))]
                })

        stats["_raw_facets"] = raw_facets
        stats["total_count"] = len(products)
        stats["duplicates_removed"] = 0
        
        return self._deduplicate(products), stats

    def _parse_price_text(self, text: str) -> int | None:
        cleaned = re.sub(r'[₹,\s]', '', text)
        cleaned = re.sub(r'(?i)INR|Rs\.?', '', cleaned)
        m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if m:
            val = float(m.group(1))
            if 10 <= val <= 10_000_000:
                return int(val)
        return None

    def _to_key(self, name: str) -> str:
        key = re.sub(r'[^a-z0-9\s]', '', name.lower().strip())
        return re.sub(r'\s+', '_', key).strip('_')[:40]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASS 2: GeMFilterScraper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GeMFilterScraper:
    """
    Extracts currently available golden filter options from the GeM facets API.

    Must be re-called after every filter state change — filters cascade
    (applying one changes the valid values for others). Never cache across
    filter state changes.
    """

    def __init__(
        self,
        session: requests.Session,
        category_url: str,
        active_filters: Optional[dict] = None,
        fragment_params: Optional[dict] = None,
    ):
        self._session = session
        self._base_url = _clean_category_url(category_url)
        self._active_filters = dict(active_filters or {})
        self._fragment_params = dict(fragment_params or {})

    def scrape_filters(self, products: Optional[list] = None, my_specs: Optional[dict] = None) -> dict:
        """
        Fetch page 1 with current filters and extract golden filter options.

        Returns:
        {
            "filter_code": {
                "name": "Human-readable name",
                "values": ["val1", "val2", ...]
            },
            ...
        }
        """
        params = {"page": 1, "format": "json"}
        for k, v in self._fragment_params.items():
            if k.lower() not in ("page", "format"):
                params[k] = v
        params.update(self._active_filters)

        url = f"{self._base_url}?{urlencode(params)}"

        for attempt in range(_MAX_FETCH_RETRIES):
            try:
                text = _fetch_with_backoff(self._session, url).strip()
                if text.startswith("{"):
                    data = json.loads(text)
                    return self.scrape_filters_from_facets(data.get("facets", {}), products, my_specs)
            except Exception as e:
                logger.warning(f"[FilterScraper] Attempt {attempt + 1} failed: {e}")
                if attempt < _MAX_FETCH_RETRIES - 1:
                    time.sleep(min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX))

        logger.error("[FilterScraper] All attempts exhausted. Returning empty.")
        return {}

    def scrape_filters_from_facets(
        self,
        raw_facets: dict,
        products: Optional[list] = None,
        my_specs: Optional[dict] = None,
    ) -> dict:
        """
        Extract filters from already-fetched facets (avoids extra API call
        when the caller already has page 1 data from GeMCategoryScraper).
        Populates values using both the facet's own values and the values extracted
        from the products' golden_params or my_specs.
        """
        filters = self._extract_golden_filters(raw_facets)
        
        # Populate from my_specs (Level 2.1)
        if my_specs:
            for spec_name, spec_val in my_specs.items():
                if not spec_val or len(spec_val) > 150:
                    continue
                for code, info in filters.items():
                    if _names_match(spec_name, info["name"]):
                        if spec_val not in info["values"]:
                            info["values"].append(spec_val)
                        break

        # Populate from products' golden_params (Level 2.2)
        if products:
            for p in products:
                golden_params = p.get("golden_params", {})
                for spec_name, spec_val in golden_params.items():
                    if not spec_val or len(spec_val) > 150:
                        continue
                    for code, info in filters.items():
                        if _names_match(spec_name, info["name"]):
                            if spec_val not in info["values"]:
                                info["values"].append(spec_val)
                            break

        # Filter out filters that still have no values
        return {code: info for code, info in filters.items() if info["values"]}

    @staticmethod
    def _extract_golden_filters(facets: dict) -> dict:
        """Parse facets JSON into {code: {"name": ..., "values": [...]}}."""
        result = {}

        for section_key in ("product specifications", "administrative"):
            section = facets.get(section_key, {})
            for facet in section.get("facet_list", []):
                code = facet.get("code", "")
                css_class = facet.get("css_class", "")
                name = facet.get("name", "")

                if len(name) > 80:
                    continue

                # Determine if golden
                is_golden = css_class == "golden"
                if not is_golden:
                    name_lower = name.lower()
                    is_golden = any(
                        k in name_lower for k in
                        ("make in india", "startup", "pac")
                    )

                if not is_golden or not code:
                    continue

                # Skip MSE — only manufacturers can use it
                if code == "mse_applicable":
                    continue

                values = GeMFilterScraper._pull_values(facet)
                result[code] = {
                    "name": name,
                    "values": values,
                }

        return result

    @staticmethod
    def _pull_values(facet: dict) -> list:
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASS 3: L1ChainSurpasser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class L1ChainSurpasser:
    """
    Sequential L1 Chain Elimination Engine.

    The algorithm is greedy-sequential, not batch:
      1. Full scrape → identify cheapest competitor (current L1)
      2. If my price is already L1 → WIN
      3. Try each golden filter value → full re-scrape to verify
         - Skip if my product disappears from results
         - Skip if seller_count < 3 (GeM comparison rule)
         - Accept if current L1 is eliminated
      4. Commit the winning filter, loop back to step 1
      5. If no single filter works → try 2-combinations
      6. If still stuck → log as "unbypassable" and STOP

    Every filter state change triggers a complete re-scrape from page 1.
    """

    MAX_ITERATIONS = 15
    MAX_TIME = 900   # 15 min hard ceiling
    MIN_SELLERS = 3  # GeM rule: comparison invalid under 3 sellers

    def __init__(self, category_url: str, my_catalogue_id: str, my_price: int):
        self._raw_url = category_url
        self._base_url = _clean_category_url(category_url)
        self._fragment_params = _extract_fragment_params(category_url)
        self._my_catalogue_id = str(my_catalogue_id)
        self._my_price = my_price

        self._session = _create_session()
        self._active_filters: dict = {}
        self._iteration_log: list = []
        self._api_calls = 0
        self._t_start = 0.0
        self._my_specs: dict = {}

    def _fetch_my_specs(self, product_url: str) -> dict:
        """
        Fetch my product's detail page and extract its specifications.
        """
        from bs4 import BeautifulSoup
        logger.info(f"[L1Surpass] Fetching my product specs from {product_url}...")
        try:
            html = _fetch_with_backoff(self._session, product_url)
            soup = BeautifulSoup(html, "html.parser")
            
            specs = {}
            feature_groups = soup.select_one("#feature_groups")
            if feature_groups:
                for table in feature_groups.find_all("table"):
                    for row in table.find_all("tr"):
                        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                        if len(cells) >= 2 and cells[0] and cells[1]:
                            specs[cells[0].strip()] = cells[1].strip()

            specs_div = soup.select_one(".specifications")
            if specs_div:
                for pc in specs_div.select(".param-container"):
                    key_el = pc.select_one(".key_name")
                    val_el = pc.select_one(".key_value")
                    if key_el and val_el:
                        name = key_el.get_text(strip=True)
                        val = val_el.get_text(strip=True)
                        if name and val and name not in specs:
                            specs[name] = val
                            
            logger.info(f"[L1Surpass] Successfully extracted {len(specs)} specs for my product.")
            return specs
        except Exception as e:
            logger.error(f"[L1Surpass] Failed to fetch my product specs: {e}")
            return {}

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Execute the full L1 elimination chain.
        Returns structured result with complete iteration logs.
        """
        self._t_start = time.time()

        logger.info(
            f"[L1Surpass] START: price=Rs. {self._my_price:,}, "
            f"id={self._my_catalogue_id}, url={self._base_url}"
        )

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            # Time check
            if time.time() - self._t_start > self.MAX_TIME:
                logger.warning("[L1Surpass] Time limit reached.")
                return self._build_result("timeout")

            # ── Step 1: Full scrape with current filters ─────────────────────
            scraper = GeMCategoryScraper(
                self._session, self._base_url,
                self._active_filters, self._my_catalogue_id,
                self._fragment_params,
                max_price=self._my_price,
            )

            try:
                full_data = scraper.scrape()
                self._api_calls += full_data["scrape_stats"]["pages_fetched"]
            except (DataInstabilityError, IncompleteScrapeError) as e:
                logger.error(f"[L1Surpass] Scrape failed at iteration {iteration}: {e}")
                self._iteration_log.append({
                    "iteration": iteration,
                    "error": str(e),
                    "result": "scrape_failed",
                    "active_filters": dict(self._active_filters),
                })
                return self._build_result("scrape_failed")

            # If we don't have our product specs yet, fetch them (Level 3)
            if not self._my_specs:
                my_product = full_data.get("my_product")
                if my_product and my_product.get("product_url"):
                    self._my_specs = self._fetch_my_specs(my_product["product_url"])

            products = full_data["products"]

            # No products at all → untapped niche
            if not products:
                logger.info("[L1Surpass] WIN: untapped niche (0 products).")
                return self._build_result(
                    "win_untapped",
                    final_rank=None,
                    total_products=0,
                )

            # ── Step 2: Find current L1 blocker ──────────────────────────────
            current_L1 = None
            for p in products:
                if p["price"] < self._my_price:
                    if self._my_catalogue_id not in p["catalogue_id"]:
                        current_L1 = p
                        break

            if current_L1 is None:
                # I AM L1!
                logger.info(
                    f"[L1Surpass] WIN: I am L1 at Rs. {self._my_price:,}! "
                    f"Rank: {full_data.get('my_product_rank')}"
                )
                return self._build_result(
                    "win",
                    final_rank=full_data.get("my_product_rank"),
                    total_products=len(products),
                    niche_min_price=products[0]["price"] if products else None,
                )

            logger.info(
                f"[L1Surpass] Iter {iteration}: L1='{current_L1['name'][:40]}' "
                f"Rs. {current_L1['price']:,} (id={current_L1['catalogue_id']})"
            )

            # ── Step 3: Get live filter options ──────────────────────────────
            # Reuse facets from the scrape if available (saves 1 API call)
            raw_facets = full_data["scrape_stats"].get("_raw_facets", {})
            if raw_facets:
                filter_scraper = GeMFilterScraper(
                    self._session, self._base_url,
                    self._active_filters, self._fragment_params,
                )
                filter_options = filter_scraper.scrape_filters_from_facets(raw_facets, products, self._my_specs)
            else:
                filter_scraper = GeMFilterScraper(
                    self._session, self._base_url,
                    self._active_filters, self._fragment_params,
                )
                filter_options = filter_scraper.scrape_filters(products, self._my_specs)
                self._api_calls += 1

            if not filter_options:
                logger.warning("[L1Surpass] No golden filter options available.")
                self._iteration_log.append({
                    "iteration": iteration,
                    "target_L1": {
                        "catalogue_id": current_L1["catalogue_id"],
                        "price": current_L1["price"],
                    },
                    "result": "no_filters_available",
                    "active_filters": dict(self._active_filters),
                })
                return self._build_result("stuck_no_filters")

            # ── Step 4: Try single filters (my-product-first ordering) ───────
            my_product = full_data.get("my_product")
            my_golden = my_product.get("golden_params", {}) if my_product else {}

            found = self._try_single_filters(
                iteration, current_L1, filter_options, my_golden
            )
            if found:
                continue  # committed, loop again

            # ── Step 5: Try 2-combinations ───────────────────────────────────
            found = self._try_two_combinations(
                iteration, current_L1, filter_options
            )
            if found:
                continue

            # ── Step 6: Stuck — this L1 is unbypassable ──────────────────────
            logger.info(
                f"[L1Surpass] STUCK: '{current_L1['name'][:40]}' "
                f"Rs. {current_L1['price']:,} is unbypassable"
            )
            self._iteration_log.append({
                "iteration": iteration,
                "target_L1": {
                    "catalogue_id": current_L1["catalogue_id"],
                    "price": current_L1["price"],
                },
                "result": "unbypassable",
                "active_filters": dict(self._active_filters),
            })
            return self._build_result(
                "stuck",
                stuck_at={"catalogue_id": current_L1["catalogue_id"],
                          "price": current_L1["price"],
                          "name": current_L1["name"]},
            )

        return self._build_result("max_iterations")

    # ── Single-filter pass ───────────────────────────────────────────────────

    def _try_single_filters(
        self,
        iteration: int,
        current_L1: dict,
        filter_options: dict,
        my_golden: dict,
    ) -> bool:
        """
        Try each unused golden filter value. My-product-first ordering:
        values matching my product's own golden_params are tried first
        (safest — guaranteed to include me).

        Returns True if a filter was committed.
        """
        # Build ordered candidate list: (code, name, value, is_my_value)
        candidates: list[tuple] = []

        for code, info in filter_options.items():
            if code in self._active_filters:
                continue  # already applied

            # Check if my product has a value for this filter
            my_val = None
            for param_name, param_val in my_golden.items():
                if _names_match(param_name, info["name"]):
                    my_val = param_val
                    break

            # My value goes first
            if my_val and my_val in info["values"]:
                candidates.insert(0, (code, info["name"], my_val, True))

            # Then all other values
            for val in info["values"]:
                if val == my_val:
                    continue
                candidates.append((code, info["name"], val, False))

        for code, name, val, is_my_val in candidates:
            if time.time() - self._t_start > self.MAX_TIME:
                break

            tentative = dict(self._active_filters)
            tentative[code] = val

            result = self._verify_filter_candidate(tentative, current_L1)

            log_entry = {
                "iteration": iteration,
                "target_L1": {
                    "catalogue_id": current_L1["catalogue_id"],
                    "price": current_L1["price"],
                },
                "filter_tried": {name: val},
                "is_my_value": is_my_val,
                "active_filters": dict(tentative),
                "scrape_stats": result.get("scrape_stats", {}),
            }

            if result["status"] == "my_product_missing":
                log_entry["result"] = "skipped_no_my_product"
                self._iteration_log.append(log_entry)
                continue

            if result["status"] == "too_few_sellers":
                log_entry["result"] = "skipped_min_sellers"
                log_entry["seller_count"] = result.get("seller_count", 0)
                self._iteration_log.append(log_entry)
                continue

            if result["status"] == "l1_eliminated":
                # COMMIT this filter
                self._active_filters = tentative
                log_entry["result"] = "eliminated"
                log_entry["new_L1"] = result.get("new_L1")
                log_entry["my_product_rank"] = result.get("my_rank")
                self._iteration_log.append(log_entry)

                new_l1_info = result.get("new_L1") or {}
                new_price = new_l1_info.get("price")
                new_price_str = f"Rs. {new_price:,}" if isinstance(new_price, (int, float)) else "None"
                logger.info(
                    f"[L1Surpass] ✅ Eliminated via {name}={val}. "
                    f"New L1: {new_price_str}"
                )
                return True

            # Not eliminated — log and continue
            log_entry["result"] = "not_eliminated"
            self._iteration_log.append(log_entry)

        return False

    # ── Two-combination fallback ─────────────────────────────────────────────

    def _try_two_combinations(
        self,
        iteration: int,
        current_L1: dict,
        filter_options: dict,
    ) -> bool:
        """
        Try all 2-combinations of unused filter values.
        Capped at 50 combinations to avoid explosion.
        Returns True if a combination was committed.
        """
        unused: list[tuple] = []
        for code, info in filter_options.items():
            if code in self._active_filters:
                continue
            # Cap at 3 values per filter to keep combinations manageable
            for val in info["values"][:3]:
                unused.append((code, info["name"], val))

        # Generate 2-combinations, skip pairs from the same filter key
        combos = [
            (a, b) for a, b in itertools.combinations(unused, 2)
            if a[0] != b[0]
        ]
        combos = combos[:50]  # hard cap

        if not combos:
            return False

        logger.info(
            f"[L1Surpass] Trying {len(combos)} 2-combinations..."
        )

        for (code_a, name_a, val_a), (code_b, name_b, val_b) in combos:
            if time.time() - self._t_start > self.MAX_TIME:
                break

            tentative = dict(self._active_filters)
            tentative[code_a] = val_a
            tentative[code_b] = val_b

            result = self._verify_filter_candidate(tentative, current_L1)

            log_entry = {
                "iteration": iteration,
                "target_L1": {
                    "catalogue_id": current_L1["catalogue_id"],
                    "price": current_L1["price"],
                },
                "filter_tried": {name_a: val_a, name_b: val_b},
                "active_filters": dict(tentative),
                "scrape_stats": result.get("scrape_stats", {}),
                "result": result["status"],
            }

            if result["status"] == "l1_eliminated":
                self._active_filters = tentative
                log_entry["result"] = "eliminated"
                log_entry["new_L1"] = result.get("new_L1")
                log_entry["my_product_rank"] = result.get("my_rank")
                self._iteration_log.append(log_entry)

                logger.info(
                    f"[L1Surpass] ✅ 2-combo: {name_a}={val_a} + "
                    f"{name_b}={val_b}"
                )
                return True

            self._iteration_log.append(log_entry)

        return False

    # ── Filter verification (full re-scrape) ─────────────────────────────────

    def _verify_filter_candidate(
        self, tentative_filters: dict, current_L1: dict
    ) -> dict:
        """
        Full re-scrape with tentative filters. Checks:
          1. My product is still in the result set
          2. At least 3 unique sellers (GeM comparison rule)
          3. The current L1 blocker is no longer present

        Every verification is a complete fresh scrape from page 1.
        No partial scrapes, no reuse of previous pages.
        """
        scraper = GeMCategoryScraper(
            self._session, self._base_url,
            tentative_filters, self._my_catalogue_id,
            self._fragment_params,
            max_price=self._my_price,
        )

        try:
            data = scraper.scrape()
            self._api_calls += data["scrape_stats"]["pages_fetched"]
        except Exception as e:
            return {
                "status": "scrape_error",
                "error": str(e),
                "scrape_stats": {},
            }

        products = data["products"]
        stats = data["scrape_stats"]

        # No products at all — this filter wipes everything
        if not products:
            return {"status": "l1_eliminated", "new_L1": None,
                    "my_rank": None, "scrape_stats": stats}

        # Check 1: is my product still present?
        if self._my_catalogue_id:
            my_present = any(
                self._my_catalogue_id in p["catalogue_id"]
                for p in products
            )
            if not my_present:
                return {"status": "my_product_missing", "scrape_stats": stats}

        # Check 2: minimum seller count
        unique_sellers = {
            p["seller_id"] for p in products if p["seller_id"]
        }
        if len(unique_sellers) < self.MIN_SELLERS:
            return {
                "status": "too_few_sellers",
                "seller_count": len(unique_sellers),
                "scrape_stats": stats,
            }

        # Check 3: is the current L1 eliminated?
        l1_still_present = any(
            p["catalogue_id"] == current_L1["catalogue_id"]
            for p in products
        )

        if l1_still_present:
            return {"status": "not_eliminated", "scrape_stats": stats}

        # SUCCESS: L1 is gone. Find the new L1.
        new_L1 = None
        for p in products:
            if p["price"] < self._my_price:
                if self._my_catalogue_id not in p["catalogue_id"]:
                    new_L1 = {
                        "catalogue_id": p["catalogue_id"],
                        "price": p["price"],
                        "name": p.get("name", ""),
                    }
                    break

        return {
            "status": "l1_eliminated",
            "new_L1": new_L1,
            "my_rank": data.get("my_product_rank"),
            "scrape_stats": stats,
        }

    # ── Result builder ───────────────────────────────────────────────────────

    def _build_result(self, status: str, **kwargs) -> dict:
        """Build the final structured result."""
        elapsed = time.time() - self._t_start
        return {
            "status": status,
            "active_filters": dict(self._active_filters),
            "iteration_log": self._iteration_log,
            "total_iterations": len({
                entry["iteration"]
                for entry in self._iteration_log
                if "iteration" in entry
            }),
            "total_api_calls": self._api_calls,
            "elapsed_seconds": round(elapsed, 1),
            "my_price": self._my_price,
            "my_catalogue_id": self._my_catalogue_id,
            **kwargs,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """
    CLI entry point.
    Usage: python l1_surpasser.py <category_url> <my_catalogue_id> <my_price>
    """
    import sys

    if len(sys.argv) < 4:
        print(
            "Usage: python l1_surpasser.py <category_url> "
            "<my_catalogue_id> <my_price>"
        )
        print(
            "Example: python l1_surpasser.py "
            "https://mkp.gem.gov.in/dental-chair/search 5116877 498599"
        )
        sys.exit(1)

    category_url = sys.argv[1]
    my_catalogue_id = sys.argv[2]
    my_price = int(sys.argv[3])

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(f"\n{'=' * 80}")
    print(f"L1 CHAIN SURPASSER")
    print(f"{'=' * 80}")
    print(f"  Category:     {category_url}")
    print(f"  My Catalogue: {my_catalogue_id}")
    print(f"  My Price:     Rs. {my_price:,}")
    print(f"{'=' * 80}\n")

    surpasser = L1ChainSurpasser(category_url, my_catalogue_id, my_price)
    result = surpasser.run()

    print(f"\n{'=' * 80}")
    print(f"FINAL RESULT: {result['status'].upper()}")
    print(f"{'=' * 80}")

    if result["active_filters"]:
        print("\nWinning filter combination:")
        for k, v in result["active_filters"].items():
            print(f"  {k} = {v}")
    else:
        print("\nNo filters applied.")

    print(f"\nTotal API calls: {result['total_api_calls']}")
    print(f"Elapsed: {result['elapsed_seconds']}s")

    print(f"\n{'─' * 80}")
    print("COMPLETE ITERATION LOG:")
    print(f"{'─' * 80}")
    print(json.dumps(result["iteration_log"], indent=2, default=str))

    print(f"\n{'─' * 80}")
    print("FULL RESULT (JSON):")
    print(f"{'─' * 80}")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
