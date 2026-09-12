"""
GeMScraper — chain-hunt and surgical-strike engine over GeM's search JSON API.

All network I/O goes through crawler.BrowserManager (a shared Playwright
browser), because GeM's WAF blocks plain `requests` calls. Category-listing
scrapes for /api/scrape live in crawler.GeMCrawler.
"""
import json
import time
import logging
from urllib.parse import urlparse, urlencode

from bs4 import BeautifulSoup

from gem_utils import (
    HTML_PARSER,
    build_product_url,
    extract_inline_specs,
    extract_specs_from_soup,
    make_name_resolver,
    names_match,
    normalize_filter_value,
    parse_fragment_params,
    parse_price,
    pull_facet_values,
    to_key,
)

logger = logging.getLogger("gem-optimizer")


class GeMScraper:

    def __init__(self):
        self._product_specs_cache = {}

    # Shared helpers, exposed as methods because chain_hunt.py's functions
    # are bound onto this class and call them through `self`.
    _names_match = staticmethod(names_match)
    _to_key = staticmethod(to_key)
    _build_product_url = staticmethod(build_product_url)
    _extract_inline_specs = staticmethod(extract_inline_specs)

    def _normalize_url(self, url: str) -> tuple[str, dict]:
        """
        Normalize a GeM URL. Handles:
          1. Auto-prepend https:// if no protocol
          2. Fragment-based query strings (search#/?q=XXX&page=1)
        Returns (clean_base_url, extra_query_params_dict)
        """
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        parsed = urlparse(url)
        extra_params = parse_fragment_params(parsed.fragment)
        clean_url = parsed._replace(fragment="", query="").geturl()
        return clean_url, extra_params

    # ── FAST PRICE SCRAPE ────────────────────────────────────────────────────

    def _fast_price_scrape(self, url: str, extra_params: dict, location: str) -> dict:
        """
        Min price and total result count for a filtered category listing.

        Requests the listing sorted price-ascending (the same sort_type
        chain_hunt.py and crawler.py rely on), so page 1 already contains
        the cheapest product -- one request instead of walking every page.
        """
        base_url = url.split("#")[0].split("?")[0]
        if not base_url.endswith("/search"):
            base_url = base_url.rstrip("/")

        query = {"page": 1, "format": "json", "sort_type": "price_in_asc"}
        for k, v in (extra_params or {}).items():
            if k.lower() not in ("page", "format", "sort_type"):
                query[k] = normalize_filter_value(v)
        if location and location.lower() not in ("", "all india", "all"):
            query["localized_search"] = location

        # A fetch failure or WAF block page is NOT an empty niche -- flag it so
        # callers don't report "0 competitors" for a check that never ran.
        failed = {"min_price": None, "total": 0, "product_count": 0, "error": True}
        try:
            text = self._fetch(f"{base_url}?{urlencode(query)}").strip()
            if not text.startswith("{"):
                logger.warning(f"[FastPrice] Non-JSON response for {base_url}: {text[:200]!r}")
                return failed
            data = json.loads(text)
        except Exception as e:
            logger.warning(f"[FastPrice] Price check failed for {base_url}: {e}")
            return failed

        prices = [
            price for c in data.get("catalogs", [])
            if (price := int(c.get("final_price", {}).get("value", 0))) > 0
        ]
        return {
            "min_price":     min(prices) if prices else None,
            "total":         data.get("number_of_results", 0),
            "product_count": len(prices),
            "error":         False,
        }

    # ── FACETS ───────────────────────────────────────────────────────────────

    def _extract_facet_defs(self, facets: dict) -> list:
        """Extract facet definitions -- and their values, when the API includes them."""
        defs = []

        for facet in facets.get("product specifications", {}).get("facet_list", []):
            name = facet.get("name", "")
            if len(name) > 200:
                continue
            defs.append({
                "filterName":  name,
                "filterKey":   facet.get("code", ""),
                "isGolden":    facet.get("css_class", "") == "golden",
                "type":        facet.get("type", ""),
                "facetValues": pull_facet_values(facet),
            })

        for facet in facets.get("administrative", {}).get("facet_list", []):
            name = facet.get("name", "")
            is_golden = any(k in name.lower() for k in ("make in india", "mse", "startup", "pac"))
            if is_golden or name in ("Make in India", "Lead Time for Dispatch"):
                defs.append({
                    "filterName":  name,
                    "filterKey":   facet.get("code", ""),
                    "isGolden":    is_golden,
                    "type":        facet.get("type", ""),
                    "facetValues": pull_facet_values(facet),
                })

        return defs

    # ── Surgical Strike: Target a specific competitor ─────────────────────────

    def surgical_strike(self, product_url: str, category_url: str,
                        target_price: int, golden_filters: list,
                        location: str = "") -> dict:
        """
        Analyze a specific competitor product and find golden filters
        to exclude it from the niche.

        1. Scrape the competitor's product detail page for specs
        2. Match specs against golden filter names
        3. For each golden filter, identify which value the competitor has
        4. Suggest applying a DIFFERENT value to exclude them
        5. Verify each suggestion by scraping the category with that filter
        """
        t_start = time.time()

        # Step 1: Fetch competitor product page and extract specs
        logger.info(f"[SurgicalStrike] Fetching competitor: {product_url}")
        try:
            html = self._fetch(product_url)
            soup = BeautifulSoup(html, HTML_PARSER)
        except Exception as e:
            return {"error": f"Failed to fetch product page: {e}"}

        raw_specs = extract_specs_from_soup(soup)
        if not raw_specs:
            return {"error": "Could not extract specs from the product page. Make sure it's a valid GeM product detail URL."}

        product_name = ""
        name_el = soup.select_one("h1, .product-name, .product-title, [class*='product'] h2")
        if name_el:
            product_name = name_el.get_text(strip=True)[:120]

        product_price = None
        price_el = soup.select_one(".price, [class*='price'], .final-price")
        if price_el:
            product_price = parse_price(price_el.get_text(strip=True))

        logger.info(f"[SurgicalStrike] Extracted {len(raw_specs)} specs from product")

        # Step 2: Build golden filter lookup (exclude MSE)
        golden_map = {}
        for gf in golden_filters:
            if gf.get("isGolden") and gf.get("filterKey") != "mse_applicable":
                golden_map[gf["filterKey"]] = {
                    "filterName": gf["filterName"],
                    "filterKey": gf["filterKey"],
                    "values": gf.get("values", []) or gf.get("facetValues", []),
                }

        # Step 3: Match competitor specs to golden filters
        matches = []
        for spec_name, spec_value in raw_specs.items():
            for gf_key, gf_info in golden_map.items():
                if names_match(spec_name, gf_info["filterName"]):
                    matches.append({
                        "filterKey": gf_key,
                        "filterName": gf_info["filterName"],
                        "competitorValue": spec_value,
                        "availableValues": gf_info["values"],
                        "specName": spec_name,
                    })
                    break

        logger.info(f"[SurgicalStrike] Matched {len(matches)} golden filters")

        # Step 4: For each matched filter, find counter-values that exclude competitor
        category_url_clean, base_extra = self._normalize_url(category_url)
        counter_filters = []
        api_calls = 0
        failed_checks = 0

        # A location or a category-URL query narrows the search beyond the single
        # counter-filter, so an empty result there could be genuine. Without one,
        # an empty result cannot be (see the verification note below).
        has_extra_scope = bool(base_extra) or bool(
            location and location.lower() not in ("", "all india", "all")
        )

        # Unfiltered total for this category. GeM silently ignores a filter key
        # it doesn't recognise and answers for the whole category, so a check
        # that matches this number verified nothing.
        baseline = self._fast_price_scrape(category_url_clean, dict(base_extra or {}), location)
        baseline_total = 0 if baseline.get("error") else baseline.get("total", 0)
        api_calls += 1

        for match in matches:
            competitor_val = match["competitorValue"].strip()

            for alt_val in match["availableValues"]:
                alt_val_clean = str(alt_val).strip()
                if alt_val_clean.lower() == competitor_val.lower():
                    continue

                # Verify: scrape with this filter value to check if competitor is excluded
                params = {match["filterKey"]: alt_val_clean}
                if base_extra:
                    params.update(base_extra)

                scrape_result = self._fast_price_scrape(category_url_clean, params, location)
                api_calls += 1
                if scrape_result.get("error"):
                    failed_checks += 1
                    logger.warning(
                        f"[SurgicalStrike] Counter-filter check failed for "
                        f"{match['filterKey']}={alt_val_clean}"
                    )
                    continue

                total = scrape_result.get("total", 0)
                min_price = scrape_result.get("min_price")

                # Zero results is NOT an untapped niche. These filter values come
                # from this category's own listings, so GeM returning nothing for
                # one of them means its search index doesn't accept the literal
                # text -- the same rejection the chain hunt flags as "unconfirmed".
                # Confirmed live: 168 of 244 printers in a category are
                # "Monochrome (Black)", yet querying that value returns 0.
                # Reporting that as an empty niche sends the seller after a niche
                # that does not exist.
                if baseline_total and total == baseline_total:
                    verification = "ignored"
                elif total > 0:
                    verification = "confirmed"
                elif has_extra_scope:
                    verification = "unverified"
                else:
                    verification = "unrecognized"

                counter_filters.append({
                    "filterKey": match["filterKey"],
                    "filterName": match["filterName"],
                    "competitorValue": competitor_val,
                    "counterValue": alt_val_clean,
                    "resultTotal": total,
                    "resultMinPrice": min_price,
                    "wouldWin": (verification == "confirmed"
                                 and min_price is not None and min_price > target_price),
                    "verification": verification,
                })

        # Sort: wins first, then verified non-wins, then anything unverified
        _rank = {"confirmed": 1, "unrecognized": 2, "unverified": 2, "ignored": 3}
        counter_filters.sort(key=lambda x: (
            0 if x["wouldWin"] else _rank.get(x["verification"], 3),
            -(x["resultMinPrice"] or 0),
        ))

        return {
            "competitorName": product_name,
            "competitorPrice": product_price,
            "competitorUrl": product_url,
            "rawSpecs": raw_specs,
            "goldenMatches": matches,
            "counterFilters": counter_filters,
            "totalApiCalls": api_calls,
            "failedChecks": failed_checks,
            "elapsed": round(time.time() - t_start, 1),
            "wins": sum(1 for cf in counter_filters if cf["wouldWin"]),
            "unverified": sum(1 for cf in counter_filters if cf["verification"] != "confirmed"),
        }

    def _enrich_single_product(self, product: dict, name_to_code: dict) -> dict:
        """Fetch specs for a single product (used by thread pool)."""
        url = product.get("productUrl") or product.get("product_url")
        if not url:
            return product
        if url in self._product_specs_cache:
            product["specs"] = self._product_specs_cache[url]
            return product
        try:
            html = self._fetch(url)
            raw_specs = extract_specs_from_soup(BeautifulSoup(html, HTML_PARSER))
            resolve_name = make_name_resolver(name_to_code)

            matched_specs = {}
            for spec_name, spec_value in raw_specs.items():
                if not spec_value or len(spec_value) > 150:
                    continue
                facet_name = resolve_name(spec_name)
                if facet_name:
                    matched_specs[name_to_code[facet_name]] = spec_value
                else:
                    matched_specs[to_key(spec_name)] = spec_value

            self._product_specs_cache[url] = matched_specs
            product["specs"] = matched_specs
        except Exception as e:
            logger.warning(f"[Enrich] Failed to fetch/parse specs for {url}: {e}")
        return product

    # ── SMART L1 HUNT (Sequential Chain Elimination) ────────────────────────────
    # Methods imported from chain_hunt.py for cleaner organization.

    from chain_hunt import _chain_scrape, smart_l1_discovery

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _fetch(self, url: str, retries: int = 3) -> str:
        """
        Fetch a URL through the shared Playwright browser (needed to bypass
        GeM's WAF, which blocks plain HTTP clients).

        Delegates to BrowserManager.fetch(), which runs the browser I/O on its
        own background event-loop thread and blocks this calling thread for
        the result. Safe to call from a ThreadPoolExecutor worker.
        """
        from crawler import BrowserManager
        return BrowserManager.get_instance().fetch(url, timeout=30000, retries=retries)
