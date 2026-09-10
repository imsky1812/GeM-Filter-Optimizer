"""
l1_surpasser.py — Hardened L1 Chain Surpasser Engine

Production-grade GeM (gem.gov.in) scraping and sequential L1 elimination.

Architecture:
  GeMCategoryScraper — full paginated scrape with 7 failure mode defenses
  GeMFilterScraper   — live golden filter option extraction from facets
  L1ChainSurpasser   — greedy-sequential elimination loop

All network calls go through crawler.BrowserManager (a shared Playwright
browser, since GeM's WAF blocks plain HTTP clients), which retries each
fetch and caps concurrency at 8 pages in flight.

Usage:
  python l1_surpasser.py <category_url> <my_catalogue_id> <my_price>
"""

import re
import json
import math
import time
import logging
import itertools
from typing import Optional
from urllib.parse import urlencode, urlparse

from bs4 import BeautifulSoup

from gem_utils import (
    HTML_PARSER,
    extract_inline_specs,
    extract_specs_from_soup,
    make_name_resolver,
    names_match as _names_match,
    parse_fragment_params,
    parse_price,
    pull_facet_values,
    to_key,
)

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
    return parse_fragment_params(urlparse(url.strip()).fragment)


def _fetch_with_backoff(url: str) -> str:
    """
    Fetch a URL using the persistent Playwright browser to bypass GeM's WAF.

    Delegates to BrowserManager.fetch(), which runs the browser I/O on its
    own background event-loop thread and blocks this calling thread for the
    result. Safe to call from any thread.
    """
    from crawler import BrowserManager
    return BrowserManager.get_instance().fetch(url, timeout=30000, retries=_MAX_FETCH_RETRIES)


def _fetch_many_with_backoff(urls: list) -> list:
    """
    Fetch several URLs concurrently through the shared browser. Returns a
    list aligned with `urls`; failed entries are None.
    """
    from crawler import BrowserManager
    return BrowserManager.get_instance().fetch_many(urls, timeout=30000, retries=_MAX_FETCH_RETRIES)


def _catalogue_id_matches(my_id: str, candidate_id: str) -> bool:
    """
    True if `candidate_id` is (or belongs to) the product identified by
    `my_id`. Callers may provide just a product-family id without GeM's
    "-<variant>" suffix (e.g. "5116877" for the full id
    "5116877-93229099418"), so a prefix match is intentionally supported --
    but anchored on the separator, so a shorter id can't accidentally match
    as an unrelated substring elsewhere in an unrelated longer id (e.g.
    "116877" incorrectly matching "45116877").
    """
    if not my_id:
        return False
    return candidate_id == my_id or candidate_id.startswith(my_id + "-")


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
    # Pages fetched concurrently per round. Small, because the scrape usually
    # stops early (price-sorted, capped at max_price) and every page fetched
    # past that point is a wasted request against GeM's WAF budget.
    PAGE_BATCH_SIZE = 4

    def __init__(
        self,
        category_url: str,
        active_filters: Optional[dict] = None,
        my_catalogue_id: str = "",
        fragment_params: Optional[dict] = None,
        max_price: Optional[int] = None,
    ):
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

    # ── Page fetch ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_page(page: int, text: str) -> dict:
        """
        Parse one page's JSON body. Raises ValueError(message, raw_text) for
        a non-JSON or malformed body, so _execute_full_scrape can route page
        1 into the HTML fallback.
        """
        text = text.strip()
        if not text.startswith("{"):
            raise ValueError(f"Non-JSON response from page {page} (got HTML/empty)", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # A malformed/truncated body (e.g. a partial WAF block response)
            # still starts with "{" but isn't valid JSON. json.JSONDecodeError
            # is a ValueError with only one arg, so on its own it would slip
            # past the 2-arg check in _execute_full_scrape and propagate
            # uncaught -- raise the same 2-arg shape as the "not JSON at all"
            # case so the HTML-fallback recovery handles it too.
            raise ValueError(f"Malformed JSON response from page {page}: {e}", text) from e

    def _fetch_page(self, page: int) -> dict:
        """Fetch a single JSON page."""
        return self._parse_page(page, _fetch_with_backoff(self._build_page_url(page)))

    def _fetch_pages(self, pages: list) -> list:
        """
        Fetch several JSON pages concurrently. Returns a list aligned with
        `pages`: the parsed page, or None if that page failed.
        """
        texts = _fetch_many_with_backoff([self._build_page_url(p) for p in pages])
        results = []
        for page, text in zip(pages, texts):
            if text is None:
                logger.warning(f"[Scraper] Page {page} fetch failed")
                results.append(None)
                continue
            try:
                results.append(self._parse_page(page, text))
            except ValueError as e:
                logger.warning(f"[Scraper] Page {page} fetch failed: {e.args[0]}")
                results.append(None)
        return results

    # ── Product parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_product(cat: dict) -> Optional[dict]:
        """Parse a single catalog JSON item into a normalized product dict."""
        price = int(cat.get("final_price", {}).get("value", 0))
        if price <= 0:
            return None

        seller_info = cat.get("seller", {})

        # Build product URL from the url parts array
        url_parts = cat.get("url", [])
        product_url = ""
        if url_parts and len(url_parts) >= 3:
            product_url = f"https://mkp.gem.gov.in/{'/'.join(url_parts)}"

        return {
            "catalogue_id": str(cat.get("id", "")),
            "price": price,
            "name": cat.get("title", ""),
            "brand": cat.get("brand", ""),
            "seller_id": str(seller_info.get("id", "")),
            "seller_name": seller_info.get("name", ""),
            "oem_id": str(cat.get("oem_id", "")),
            "product_url": product_url,
            "golden_params": extract_inline_specs(cat),
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
            if _catalogue_id_matches(self._my_catalogue_id, p["catalogue_id"]):
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
        except ValueError as e:
            if len(e.args) >= 2 and isinstance(e.args[1], str):
                return self._scrape_html_fallback(e.args[1], stats)
            raise

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

        # ── Remaining pages, in concurrent batches, with drift detection ─────
        # Each batch is processed in page order, so drift restarts, the empty-
        # page terminator and max_price early stopping behave exactly as they
        # would walking pages one at a time.
        restart_count = 0
        page = 2

        while page <= total_pages:
            if restart_count > self.MAX_RESTARTS:
                raise DataInstabilityError(
                    f"total_count changed {restart_count} times during scrape "
                    f"(drift: {total_count} products)"
                )

            batch = list(range(page, min(page + self.PAGE_BATCH_SIZE, total_pages + 1)))
            restarted = finished = False

            for pg, data in zip(batch, self._fetch_pages(batch)):
                # Failure Mode 5: a failed page is skipped (the completeness
                # check catches real gaps); a failed last page just ends the scrape
                if data is None:
                    continue
                stats["pages_fetched"] += 1

                # Failure Mode 1: Offset drift detection
                new_total = data.get("number_of_results", total_count)
                if new_total != total_count:
                    logger.warning(
                        f"[Scraper] DRIFT: total {total_count} -> {new_total} "
                        f"at page {pg}. Restart #{restart_count + 1}."
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
                    restarted = True
                    break

                page_catalogs = data.get("catalogs", [])

                # Failure Mode 5: empty page = end of data (not an error)
                if not page_catalogs:
                    finished = True
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
                            f"[Scraper] Early stopping at page {pg} because minimum page price "
                            f"Rs. {min(current_page_prices):,} exceeds max_price Rs. {self._max_price:,}"
                        )
                        finished = True
                        break

            if finished:
                break
            page = 2 if restarted else batch[-1] + 1

        # Failure Mode 4: deduplicate
        products = self._deduplicate(all_raw)
        stats["duplicates_removed"] = len(all_raw) - len(products)

        return products, stats

    def _scrape_html_fallback(self, html_text: str, stats: dict) -> tuple:
        soup = BeautifulSoup(html_text, HTML_PARSER)

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
                if not m:
                    continue
                variant_id = f"{m.group(1)}-{m.group(2)}"

                name_el = card.select_one('.product-title, .title, .product-name, h5, h4, [class*="title"]')
                if not name_el:
                    name_el = link_el
                name = name_el.get_text(strip=True) if name_el else ""
                name = re.sub(r'([A-Z\s]+)\1', r'\1', name).strip()

                price = 0
                price_el = card.select_one('.final-price, .price, .offer_price, .our_price, [class*="price"]')
                if price_el:
                    price = parse_price(price_el.get_text(strip=True)) or 0

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

                filter_key = block.get('id') or block.get('data-facet') or to_key(filter_name)

                # Extract options (skip parent containers that hold other matches)
                val_elements = block.select('label, .facet-values li, [class*="option"], [class*="value"]')
                leaf_elements = [
                    el for el in val_elements
                    if not any(other is not el and other in el.descendants for other in val_elements)
                ]

                vals = []
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
                    "code": to_key(fname),
                    "css_class": "golden",
                    "type": "spec",
                    "facet_values": [{"name": v, "value": v} for v in sorted(vals)]
                })

        stats["_raw_facets"] = raw_facets
        stats["total_count"] = len(products)
        stats["duplicates_removed"] = 0

        return self._deduplicate(products), stats


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
        category_url: str,
        active_filters: Optional[dict] = None,
        fragment_params: Optional[dict] = None,
    ):
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
                text = _fetch_with_backoff(url).strip()
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

        code_by_name = {}
        for code, info in filters.items():
            code_by_name.setdefault(info["name"], code)
        seen_values = {code: set(info["values"]) for code, info in filters.items()}
        resolve_name = make_name_resolver(code_by_name)

        def add_spec_values(specs: dict):
            for spec_name, spec_val in specs.items():
                if not spec_val or len(spec_val) > 150:
                    continue
                filter_name = resolve_name(spec_name)
                if filter_name:
                    code = code_by_name[filter_name]
                    if spec_val not in seen_values[code]:
                        seen_values[code].add(spec_val)
                        filters[code]["values"].append(spec_val)

        # Populate from my_specs (Level 2.1), then products' golden_params (Level 2.2)
        if my_specs:
            add_spec_values(my_specs)
        for p in products or []:
            add_spec_values(p.get("golden_params", {}))

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
                name = facet.get("name", "")

                if len(name) > 80:
                    continue

                # Determine if golden
                is_golden = facet.get("css_class", "") == "golden"
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

                result[code] = {
                    "name": name,
                    "values": pull_facet_values(facet),
                }

        return result


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

        self._active_filters: dict = {}
        self._iteration_log: list = []
        self._api_calls = 0
        self._t_start = 0.0
        self._my_specs: dict = {}
        self._scrape_error_count = 0

    def _fetch_my_specs(self, product_url: str) -> dict:
        """
        Fetch my product's detail page and extract its specifications.
        """
        logger.info(f"[L1Surpass] Fetching my product specs from {product_url}...")
        try:
            html = _fetch_with_backoff(product_url)
            specs = extract_specs_from_soup(BeautifulSoup(html, HTML_PARSER))
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

            # Reset per-iteration so Step 6 can tell whether a "stuck" verdict
            # is based on clean verifications or was contaminated by transient
            # scrape failures during this iteration's candidate checks.
            self._scrape_error_count = 0

            # ── Step 1: Full scrape with current filters ─────────────────────
            scraper = GeMCategoryScraper(
                self._base_url,
                self._active_filters, self._my_catalogue_id,
                self._fragment_params,
                max_price=self._my_price,
            )

            try:
                full_data = scraper.scrape()
                self._api_calls += full_data["scrape_stats"]["pages_fetched"]
            except Exception as e:
                # DataInstabilityError / IncompleteScrapeError, or a fetch that
                # exhausted its retries (RuntimeError from BrowserManager) --
                # report a failed scrape instead of crashing the request.
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
            current_L1 = next(
                (p for p in products
                 if p["price"] < self._my_price
                 and not _catalogue_id_matches(self._my_catalogue_id, p["catalogue_id"])),
                None,
            )

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
            filter_scraper = GeMFilterScraper(
                self._base_url, self._active_filters, self._fragment_params,
            )
            raw_facets = full_data["scrape_stats"].get("_raw_facets", {})
            if raw_facets:
                filter_options = filter_scraper.scrape_filters_from_facets(raw_facets, products, self._my_specs)
            else:
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
            if self._scrape_error_count > 0:
                # Some candidates couldn't be verified due to transient scrape
                # failures this iteration -- a confident "unbypassable" verdict
                # would be based on incomplete data. Report the uncertainty
                # instead of a false-confident STUCK.
                logger.warning(
                    f"[L1Surpass] Cannot confidently declare '{current_L1['name'][:40]}' "
                    f"unbypassable: {self._scrape_error_count} candidate(s) hit a "
                    "scrape error this iteration and were never actually verified."
                )
                self._iteration_log.append({
                    "iteration": iteration,
                    "target_L1": {
                        "catalogue_id": current_L1["catalogue_id"],
                        "price": current_L1["price"],
                    },
                    "result": "verification_incomplete",
                    "scrape_error_count": self._scrape_error_count,
                    "active_filters": dict(self._active_filters),
                })
                return self._build_result(
                    "verification_incomplete",
                    stuck_at={"catalogue_id": current_L1["catalogue_id"],
                              "price": current_L1["price"],
                              "name": current_L1["name"]},
                )

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
            my_val = next(
                (param_val for param_name, param_val in my_golden.items()
                 if _names_match(param_name, info["name"])),
                None,
            )

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

            if result["status"] == "scrape_error":
                # Transient failure verifying this candidate -- do NOT log it
                # as "the filter doesn't help" (not_eliminated). Track it so
                # Step 6 knows a "stuck" verdict here would be unreliable.
                self._scrape_error_count += 1
                log_entry["result"] = "scrape_error"
                log_entry["error"] = result.get("error")
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

        # Generate 2-combinations, skip pairs from the same filter key (hard cap 50)
        combos = list(itertools.islice(
            ((a, b) for a, b in itertools.combinations(unused, 2) if a[0] != b[0]),
            50,
        ))

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

            if result["status"] == "scrape_error":
                self._scrape_error_count += 1

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
            self._base_url,
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

        # Note: if `products` is empty, Check 1 below correctly falls through
        # to "my_product_missing" (my own listing can't be present in an
        # empty result set either) rather than being treated as a win --
        # a filter that shows nobody, including me, is not an elimination.

        # Check 1: is my product still present?
        if self._my_catalogue_id:
            my_present = any(
                _catalogue_id_matches(self._my_catalogue_id, p["catalogue_id"])
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
        new_L1 = next(
            ({"catalogue_id": p["catalogue_id"], "price": p["price"], "name": p.get("name", "")}
             for p in products
             if p["price"] < self._my_price
             and not _catalogue_id_matches(self._my_catalogue_id, p["catalogue_id"])),
            None,
        )

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
    print("L1 CHAIN SURPASSER")
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
